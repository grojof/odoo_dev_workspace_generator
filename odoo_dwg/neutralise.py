"""Neutralising a copy of a production database, reversibly.

A copy of production is armed the moment Odoo starts on it: every cron is
overdue, a tax integration in production mode is one click from submitting real
invoices, and the copy identifies itself to Odoo's services as production.
Odoo's own ``neutralize`` exists only from 16.0, is one-way (it replaces secrets
and deletes push devices) and knows nothing of OCA modules.

This one records every value it changes — row, column, the value before, the
value set — in a table inside the database, before changing it, so production's
settings can be given back exactly. Giving them back is a separate action the
operator asks for; nothing here does it on its own.

Each rule is guarded by the existence of what it touches, so one catalogue
serves every version from 12.0 to 18.0. Pure: this module builds SQL; running
it is ``system``'s job, or the migration driver's.
"""

from __future__ import annotations

from dataclasses import dataclass

RECORD_TABLE = "odwg_neutralisation"
RUN_TABLE = "odwg_neutralisation_run"
RULE_TABLE = "odwg_neutralisation_rule"

#: Where a neutralised database's links point unless the operator says otherwise.
DEFAULT_LOCAL_URL = "http://127.0.0.1:8069"

_ODOO_NEUTRALIZE = "odoo {} {}/data/neutralize.sql"


@dataclass(frozen=True)
class Keep:
    """A cron left active: housekeeping that sends nothing."""

    xmlid: str
    reason: str


#: Crons that stay active. Matched by external identifier, never by name: names
#: are translated and edited, and a name match would keep the wrong cron alive.
HOUSEKEEPING = (
    Keep("base.autovacuum_job",
         "Odoo's own neutralisation keeps exactly this cron (odoo 16.0-19.0 "
         "odoo/addons/base/data/neutralize.sql); it vacuums internal data and calls nothing."),
    Keep("queue_job.ir_cron_autovacuum_queue_jobs",
         "Deletes old done jobs (OCA/queue queue_job/data/queue_data.xml); runs no job and "
         "calls nothing."),
)


@dataclass(frozen=True)
class Rule:
    """Set ``sets`` on the rows of ``table`` matching ``where``, recording each value first.

    ``where`` and the values are SQL over the row alias ``t``. A rule applies
    only where its table and every column it names exist. ``once`` rules act on
    a row only the first time (a fresh ``database.uuid`` is not re-rolled on
    every run); the others are re-applied whenever a value has drifted back,
    without re-recording it, so the value recorded first stays production's.
    """

    id: str
    source: str
    table: str
    model: str
    where: str
    sets: tuple[tuple[str, str], ...]
    requires: tuple[str, ...] = ()
    label: str = ""
    once: bool = False

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(("id", *self.requires, *(c for c, _ in self.sets),
                                    *((self.label,) if self.label else ()))))


@dataclass(frozen=True)
class Insert:
    """A row added when absent (``database.is_neutralized``), recorded so restore deletes it."""

    id: str
    source: str
    key: str
    value: str


def _keep_ids() -> str:
    pairs = ", ".join(f"('{k.xmlid.split('.')[0]}', '{k.xmlid.split('.')[1]}')" for k in HOUSEKEEPING)
    return (f"t.id NOT IN (SELECT res_id FROM ir_model_data WHERE model = 'ir.cron' "
            f"AND (module, name) IN ({pairs}))")


def _param(key: str) -> str:
    return f"t.key = '{key}'"


#: What a copy must not do, and where each rule comes from.
CATALOGUE: tuple[Rule, ...] = (
    Rule("crons", _ODOO_NEUTRALIZE.format("16.0-19.0", "odoo/addons/base") + " (made reversible)",
         "ir_cron", "ir.cron", f"t.active AND {_keep_ids()}", (("active", "false"),),
         label="cron_name"),
    Rule("queued-jobs", "OCA/queue 12.0 queue_job/job.py:20-24 (pending, enqueued and started "
         "are what the job runner executes; held as failed, which it never picks up)",
         "queue_job", "queue.job", "t.state IN ('pending', 'enqueued', 'started', "
         "'wait_dependencies')", (("state", "'failed'"),), label="name"),
    Rule("sii-oca", "OCA/l10n-spain 12.0 l10n_es_aeat_sii/models/res_company.py:15-16; 13.0 and "
         "18.0 l10n_es_aeat_sii_oca/models/res_company.py:17-18",
         "res_company", "res.company", "t.sii_enabled OR NOT coalesce(t.sii_test, false)",
         (("sii_enabled", "false"), ("sii_test", "true")), label="name"),
    Rule("sii-odoo", _ODOO_NEUTRALIZE.format("16.0-19.0", "addons/l10n_es_edi_sii"),
         "res_company", "res.company", "NOT coalesce(t.l10n_es_sii_test_env, false)",
         (("l10n_es_sii_test_env", "true"),), label="name"),
    Rule("ticketbai", _ODOO_NEUTRALIZE.format("17.0-19.0", "addons/l10n_es_edi_tbai"),
         "res_company", "res.company", "NOT coalesce(t.l10n_es_tbai_test_env, false)",
         (("l10n_es_tbai_test_env", "true"),), label="name"),
    Rule("edi-proxy", _ODOO_NEUTRALIZE.format("16.0-19.0", "addons/account_edi_proxy_client"),
         "account_edi_proxy_client_user", "account_edi_proxy_client.user",
         "t.edi_mode = 'prod' AND t.proxy_type NOT IN ('l10n_my_edi', 'l10n_gr_edi')",
         (("edi_mode", "CASE WHEN t.proxy_type IN ('l10n_it_edi', 'peppol', 'nemhandel', "
                       "'pdp') THEN 'demo' ELSE 'test' END"),), requires=("proxy_type",)),
    Rule("payment-provider", _ODOO_NEUTRALIZE.format("16.0-19.0", "addons/payment"),
         "payment_provider", "payment.provider", "t.state NOT IN ('test', 'disabled')",
         (("state", "'disabled'"),), label="code"),
    Rule("payment-acquirer-state", "odoo 13.0-15.0 addons/payment/models/payment_acquirer.py "
         "(state: disabled/enabled/test)", "payment_acquirer", "payment.acquirer",
         "t.state NOT IN ('test', 'disabled')", (("state", "'disabled'"),), label="provider"),
    Rule("payment-acquirer-environment", "odoo 12.0 addons/payment/models/payment_acquirer.py:85 "
         "(environment: test/prod; toggle_environment_value)", "payment_acquirer",
         "payment.acquirer", "t.environment = 'prod'", (("environment", "'test'"),),
         label="provider"),
    Rule("delivery-environment", _ODOO_NEUTRALIZE.format("16.0-19.0", "addons/delivery"),
         "delivery_carrier", "delivery.carrier", "t.prod_environment",
         (("prod_environment", "false"),)),
    Rule("delivery-external", _ODOO_NEUTRALIZE.format("16.0-19.0", "addons/delivery"),
         "delivery_carrier", "delivery.carrier",
         "t.active AND t.delivery_type NOT IN ('fixed', 'base_on_rule')",
         (("active", "false"),), requires=("delivery_type",)),
    Rule("oauth", _ODOO_NEUTRALIZE.format("16.0-19.0", "addons/auth_oauth"),
         "auth_oauth_provider", "auth.oauth.provider", "t.enabled", (("enabled", "false"),)),
    Rule("google-calendar-users", "odoo 12.0-15.0 addons/google_calendar/models/res_users.py "
         "(the tokens live on res_users until 16.0)",
         "res_users", "res.users", "t.google_calendar_rtoken IS NOT NULL OR "
         "t.google_calendar_token IS NOT NULL",
         (("google_calendar_rtoken", "NULL"), ("google_calendar_token", "NULL"))),
    Rule("google-calendar-settings", _ODOO_NEUTRALIZE.format("16.0-19.0", "addons/google_calendar"),
         "res_users_settings", "res.users.settings", "t.google_calendar_rtoken IS NOT NULL OR "
         "t.google_calendar_token IS NOT NULL",
         (("google_calendar_rtoken", "NULL"), ("google_calendar_token", "NULL"),
          ("google_synchronization_stopped", "true"))),
    Rule("microsoft-calendar-users", _ODOO_NEUTRALIZE.format("16.0-19.0",
                                                             "addons/microsoft_calendar"),
         "res_users", "res.users", "t.microsoft_calendar_token IS NOT NULL OR "
         "t.microsoft_calendar_rtoken IS NOT NULL",
         (("microsoft_calendar_token", "NULL"), ("microsoft_calendar_rtoken", "NULL"))),
    Rule("microsoft-calendar-settings", _ODOO_NEUTRALIZE.format("16.0-19.0",
                                                                "addons/microsoft_calendar"),
         "res_users_settings", "res.users.settings", "t.microsoft_calendar_sync_token IS NOT NULL",
         (("microsoft_calendar_sync_token", "NULL"), ("microsoft_synchronization_stopped",
                                                      "true"))),
    Rule("webhooks", _ODOO_NEUTRALIZE.format("17.0-19.0", "odoo/addons/base"),
         "ir_act_server", "ir.actions.server",
         "t.state = 'webhook' AND t.webhook_url IS DISTINCT FROM 'neutralised: webhook disabled'",
         (("webhook_url", "'neutralised: webhook disabled'"),), requires=("state",),
         label="name"),
    Rule("iap", _ODOO_NEUTRALIZE.format("16.0-19.0", "addons/iap"),
         "iap_account", "iap.account", "t.account_token NOT LIKE '%+disabled'",
         (("account_token", "regexp_replace(t.account_token, '(\\+.*)?$', '+disabled')"),),
         label="service_name"),
    Rule("mail-template-server", _ODOO_NEUTRALIZE.format("16.0-19.0", "addons/mail"),
         "mail_template", "mail.template", "t.mail_server_id IS NOT NULL",
         (("mail_server_id", "NULL"),)),
    Rule("website-domain", _ODOO_NEUTRALIZE.format("16.0-19.0", "addons/website"),
         "website", "website", "t.domain IS NOT NULL", (("domain", "NULL"),), label="name"),
    Rule("website-cdn", _ODOO_NEUTRALIZE.format("16.0-19.0", "addons/website"),
         "website", "website", "t.cdn_activated", (("cdn_activated", "false"),), label="name"),
    Rule("neutralised-banner", _ODOO_NEUTRALIZE.format("16.0-19.0", "addons/web"),
         "ir_ui_view", "ir.ui.view", "t.key = 'web.neutralize_banner' AND NOT t.active",
         (("active", "true"),), requires=("key",), label="key"),
    Rule("peppol-mode", _ODOO_NEUTRALIZE.format("17.0-19.0", "addons/account_peppol"),
         "ir_config_parameter", "ir.config_parameter",
         f"{_param('account_peppol.edi.mode')} AND t.value <> 'demo'", (("value", "'demo'"),),
         requires=("key",), label="key"),
    Rule("base-url", "odoo_dwg: a copy's links, portal and reports must not point at production",
         "ir_config_parameter", "ir.config_parameter", _param("web.base.url"),
         (("value", ":local_url"),), requires=("key",), label="key"),
    Rule("base-url-freeze", "odoo_dwg: a frozen base URL would keep production's after login",
         "ir_config_parameter", "ir.config_parameter", _param("web.base.url.freeze"),
         (("value", "'False'"),), requires=("key",), label="key"),
    Rule("database-uuid", "odoo_dwg: database.uuid identifies the database to odoo.com and IAP",
         "ir_config_parameter", "ir.config_parameter", _param("database.uuid"),
         (("value", "regexp_replace(md5(random()::text || clock_timestamp()::text), "
                    "'(.{8})(.{4})(.{4})(.{4})(.{12})', '\\1-\\2-\\3-\\4-\\5')"),),
         requires=("key",), label="key", once=True),
    Rule("neutralised-flag", _ODOO_NEUTRALIZE.format("16.0-19.0", "odoo/addons/base"),
         "ir_config_parameter", "ir.config_parameter",
         f"{_param('database.is_neutralized')} AND t.value IS DISTINCT FROM 'True'",
         (("value", "'True'"),), requires=("key",), label="key"),
)

INSERTS: tuple[Insert, ...] = (
    Insert("neutralised-flag-insert", _ODOO_NEUTRALIZE.format("16.0-19.0", "odoo/addons/base"),
           "database.is_neutralized", "True"),
)


def rule_tables() -> tuple[str, ...]:
    return tuple(dict.fromkeys(r.table for r in CATALOGUE))


# --- apply ---------------------------------------------------------------------------

def _lit(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _value(expr: str, local_url: str) -> str:
    return expr.replace(":local_url", _lit(local_url))


def _guard(rule: Rule) -> str:
    cols = ", ".join(_lit(c) for c in rule.columns)
    # pg_attribute, as in ``columns_sql``: existence must not depend on privileges.
    return (f"(SELECT count(*) FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
            f"JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = current_schema() "
            f"AND c.relkind = 'r' AND c.relname = {_lit(rule.table)} AND a.attnum > 0 AND NOT "
            f"a.attisdropped AND a.attname IN ({cols})) = {len(rule.columns)}")


def _xmlid(rule: Rule) -> str:
    return (f"(SELECT d.module || '.' || d.name FROM ir_model_data d WHERE d.model = "
            f"{_lit(rule.model)} AND d.res_id = t.id ORDER BY d.id LIMIT 1)")


def _recorded(rule: Rule, column: str, this_run: bool = False) -> str:
    fresh = " AND n.run = r AND n.applied IS NULL" if this_run else ""
    return (f"EXISTS (SELECT 1 FROM {RECORD_TABLE} n WHERE n.relation = {_lit(rule.table)} "
            f"AND n.row_id = t.id AND n.col = {_lit(column)}{fresh})")


def _rule_block(rule: Rule, local_url: str) -> str:
    """Record, then write, one column at a time; recorded values are never overwritten."""
    parts = []
    for column, expr in rule.sets:
        value = _value(expr, local_url)
        match = f"({rule.where}) AND t.{column} IS DISTINCT FROM {value}"
        write = match
        if rule.once:
            # Recorded, then written: the write has to find the record this run just
            # made, or it would find the row recorded and never act.
            match = f"({rule.where}) AND NOT {_recorded(rule, column)}"
            write = f"({rule.where}) AND {_recorded(rule, column, this_run=True)}"
        parts.append(
            f"INSERT INTO {RECORD_TABLE} (run, rule, relation, row_id, xmlid, col, kind, "
            f"original, applied) SELECT r, {_lit(rule.id)}, {_lit(rule.table)}, t.id, "
            f"{_xmlid(rule)}, {_lit(column)}, 'update', to_jsonb(t.{column}), NULL "
            f"FROM {rule.table} t WHERE {match} ON CONFLICT DO NOTHING; "
            f"UPDATE {rule.table} t SET {column} = {value} WHERE {write}; "
            f"UPDATE {RECORD_TABLE} n SET applied = to_jsonb(t.{column}) FROM {rule.table} t "
            f"WHERE n.relation = {_lit(rule.table)} AND n.row_id = t.id AND n.col = "
            f"{_lit(column)} AND n.applied IS NULL; "
        )
    return (f"IF {_guard(rule)} THEN {''.join(parts)}"
            f"INSERT INTO {RULE_TABLE} (run, rule, state) VALUES (r, {_lit(rule.id)}, 'applied'); "
            f"ELSE INSERT INTO {RULE_TABLE} (run, rule, state) VALUES "
            f"(r, {_lit(rule.id)}, 'not applicable'); END IF; ")


def _insert_block(ins: Insert) -> str:
    return (
        "IF to_regclass('ir_config_parameter') IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "
        f"ir_config_parameter WHERE key = {_lit(ins.key)}) THEN "
        f"WITH added AS (INSERT INTO ir_config_parameter (key, value) VALUES ({_lit(ins.key)}, "
        f"{_lit(ins.value)}) RETURNING id) INSERT INTO {RECORD_TABLE} (run, rule, relation, "
        f"row_id, xmlid, col, kind, original, applied) SELECT r, {_lit(ins.id)}, "
        f"'ir_config_parameter', id, NULL, 'value', 'insert', NULL, to_jsonb({_lit(ins.value)}::text) "
        f"FROM added; END IF; "
    )


def apply_sql(local_url: str = DEFAULT_LOCAL_URL) -> str:
    """Neutralise the connected database, recording every change. Repeatable: a
    second run records only rows and columns the first did not, so the value
    recorded first — production's — is the one a restore gives back."""
    blocks = "".join(_rule_block(rule, local_url) for rule in CATALOGUE)
    inserts = "".join(_insert_block(ins) for ins in INSERTS)
    return (
        f"CREATE TABLE IF NOT EXISTS {RUN_TABLE} (run integer PRIMARY KEY, "
        "at timestamptz NOT NULL DEFAULT now(), odoo_version text); "
        f"CREATE TABLE IF NOT EXISTS {RECORD_TABLE} (run integer NOT NULL, rule text NOT NULL, "
        "relation text NOT NULL, row_id integer NOT NULL, xmlid text, col text NOT NULL, "
        "kind text NOT NULL, original jsonb, applied jsonb, "
        "at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (relation, row_id, col)); "
        f"CREATE TABLE IF NOT EXISTS {RULE_TABLE} (run integer NOT NULL, rule text NOT NULL, "
        "state text NOT NULL, PRIMARY KEY (run, rule)); "
        "DO $$ DECLARE r integer; BEGIN "
        f"INSERT INTO {RUN_TABLE} (run, odoo_version) SELECT coalesce(max(run), 0) + 1, "
        "(SELECT latest_version FROM ir_module_module WHERE name = 'base') "
        f"FROM {RUN_TABLE} RETURNING run INTO r; "
        f"{blocks}{inserts}END $$;"
    )


# --- check ---------------------------------------------------------------------------

def applicable(existing: set[tuple[str, str]]) -> list[Rule]:
    """The rules whose table and columns exist, given ``(table, column)`` pairs."""
    return [r for r in CATALOGUE if all((r.table, c) in existing for c in r.columns)]


def columns_sql() -> str:
    """Which catalogue tables and columns exist. Writes nothing.

    From ``pg_attribute``, not ``information_schema.columns``: the latter lists
    only the columns the connected role may read, so a check run by a restricted
    role took a hidden column (``ir_config_parameter.value``) for an absent one
    and skipped its rule in silence, calling an armed database clean. Asked here,
    the column exists, the rule is checked, and a role that cannot read it gets
    a permission error — "could not tell", never "clean"."""
    tables = ", ".join(_lit(t) for t in rule_tables())
    return ("SELECT c.relname, a.attname FROM pg_attribute a JOIN pg_class c ON c.oid = "
            "a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = "
            "current_schema() AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped "
            f"AND c.relname IN ({tables})")


def check_sql(rules: list[Rule], local_url: str = DEFAULT_LOCAL_URL) -> str:
    """One row per rule with something still armed: rule, how many rows, a few of
    them by label. Only ``SELECT``; the caller passes only applicable rules."""
    parts = []
    for rule in rules:
        if rule.once:
            continue  # a fresh uuid is a courtesy to odoo.com, not something that acts
        armed = " OR ".join(f"t.{c} IS DISTINCT FROM {_value(e, local_url)}" for c, e in rule.sets)
        label = f"t.{rule.label}::text" if rule.label else "t.id::text"
        parts.append(
            f"SELECT {_lit(rule.id)}, count(*)::text, coalesce(array_to_string("
            f"(array_agg({label} ORDER BY t.id))[1:5], ', '), '') FROM {rule.table} t "
            f"WHERE ({rule.where}) AND ({armed}) HAVING count(*) > 0"
        )
    if not parts:
        return "SELECT NULL::text, NULL::text, NULL::text WHERE false"
    return " UNION ALL ".join(parts)


def guard_sql(local_url: str = DEFAULT_LOCAL_URL, capture: tuple[str, int] = ("127.0.0.1", 1025)
              ) -> str:
    """The check, for a shell script: raises, naming every rule with something
    armed, or does nothing. Each rule guarded as in ``apply_sql``, so it runs on
    any version without the caller knowing which tables exist. Writes nothing."""
    blocks = []
    for rule in CATALOGUE:
        if rule.once:
            continue
        armed = " OR ".join(f"t.{c} IS DISTINCT FROM {_value(e, local_url)}" for c, e in rule.sets)
        blocks.append(
            f"IF {_guard(rule)} THEN SELECT count(*) INTO n FROM {rule.table} t WHERE "
            f"({rule.where}) AND ({armed}); IF n > 0 THEN found := found || "
            f"{_lit(rule.id)} || ' (' || n || ') '; END IF; END IF; ")
    host, port = capture
    return (
        "DO $$ DECLARE n integer; found text := ''; BEGIN "
        f"{''.join(blocks)}"
        "IF to_regclass('ir_mail_server') IS NOT NULL THEN SELECT count(*) INTO n FROM "
        f"ir_mail_server WHERE active AND NOT (smtp_host = {_lit(host)} AND smtp_port = {port}); "
        "IF n > 0 THEN found := found || 'mail-server (' || n || ') '; END IF; END IF; "
        "IF found <> '' THEN RAISE EXCEPTION 'can still act on the outside: %', found; END IF; "
        "END $$;"
    )


@dataclass(frozen=True)
class Armed:
    """Something in the database that can still act on the outside."""

    rule: str
    count: int
    sample: str


def read_armed(rows: list[list[str]]) -> list[Armed]:
    armed = []
    for row in rows:
        if len(row) >= 3 and row[0]:
            try:
                armed.append(Armed(row[0], int(row[1]), row[2]))
            except ValueError:
                continue
    return armed


# --- restore -------------------------------------------------------------------------

def later_rows_sql() -> str:
    """Rows recorded after the first run — not in production — which a restore leaves off."""
    return (f"SELECT n.rule, n.relation, n.row_id::text, coalesce(n.xmlid, ''), n.col "
            f"FROM {RECORD_TABLE} n WHERE n.kind = 'update' AND n.run > "
            f"(SELECT min(run) FROM {RUN_TABLE}) ORDER BY n.rule, n.row_id")


def restore_sql() -> str:
    """Give production's recorded values back: the first run's records, written with
    ``jsonb_populate_record`` so no column type is spelled out. Rows and columns
    that no longer exist, and rows first recorded by a later run (not in
    production), are raised as notices and left as they are. Inserted rows are
    deleted. The record tables are dropped at the end."""
    return (
        "DO $$ DECLARE first_run integer; rec record; present boolean; BEGIN "
        f"IF to_regclass('{RECORD_TABLE}') IS NULL THEN "
        "RAISE EXCEPTION 'no neutralisation is recorded in this database'; END IF; "
        f"SELECT min(run) INTO first_run FROM {RUN_TABLE}; "
        f"FOR rec IN SELECT * FROM {RECORD_TABLE} ORDER BY run, relation, row_id, col LOOP "
        "IF rec.kind = 'insert' THEN "
        "EXECUTE format('DELETE FROM %I WHERE id = $1', rec.relation) USING rec.row_id; "
        "CONTINUE; END IF; "
        "IF rec.run > first_run THEN RAISE NOTICE 'left neutralised, not in production: "
        "% % row % (%)', rec.rule, rec.relation, rec.row_id, coalesce(rec.xmlid, '-'); "
        "CONTINUE; END IF; "
        "SELECT count(*) = 1 INTO present FROM information_schema.columns WHERE table_schema = "
        "current_schema() AND table_name = rec.relation AND column_name = rec.col; "
        "IF NOT present THEN RAISE NOTICE 'not restored, column gone: %.%', rec.relation, "
        "rec.col; CONTINUE; END IF; "
        "EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I WHERE id = $1)', rec.relation) "
        "INTO present USING rec.row_id; "
        "IF NOT present THEN RAISE NOTICE 'not restored, row gone: % row %', rec.relation, "
        "rec.row_id; CONTINUE; END IF; "
        "EXECUTE format('UPDATE %I SET %I = (jsonb_populate_record(NULL::%I, "
        "jsonb_build_object(%L, $1))).%I WHERE id = $2', rec.relation, rec.col, rec.relation, "
        "rec.col, rec.col) USING rec.original, rec.row_id; "
        "END LOOP; "
        f"DROP TABLE {RECORD_TABLE}, {RULE_TABLE}, {RUN_TABLE}; "
        "END $$;"
    )


@dataclass(frozen=True)
class LaterRow:
    rule: str
    relation: str
    row_id: str
    xmlid: str
    column: str


def read_later_rows(rows: list[list[str]]) -> list[LaterRow]:
    return [LaterRow(*row[:5]) for row in rows if len(row) >= 5]

