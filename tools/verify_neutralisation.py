#!/usr/bin/env python3
"""Execute neutralise → check → re-apply → restore against a throwaway PostgreSQL.

The unit suite asserts the SQL's text; this runs it, on databases shaped the way
Odoo's differ across a chain — 12.0 (``payment_acquirer`` with ``environment``,
the OCA SII fields, Google tokens on ``res_users``), 14.0 (Odoo's shared Spanish
test flag, OCA TicketBAI, an EDI proxy whose mode is a missing parameter, mail
queued on a named server), 16.0 (a ``prod`` EDI parameter, calendar credentials),
17.0 (VERI*FACTU, push devices, Malaysia) and 18.0 (``payment_provider``, the
split SII/TicketBAI flags, webhooks, OAuth, cloud storage, certificates, an IAP
account with no stored service name) — and asserts what the operator depends on:

- after neutralising, the check finds nothing that can act, and the housekeeping
  crons are still active;
- the check counts every armed row, not a sample;
- a cron a module update switches back on, and one a migration step creates, are
  turned off by the next run, and the first record of production's value stays;
- what Odoo deletes (push devices, cloud storage settings) is made inert instead,
  and a parameter that is missing (14.0-16.0's EDI proxy mode) is added;
- a restore gives back production's rows column for column, leaves the cron
  production never had switched off, deletes what was inserted, and drops its
  tables; a restore on a database never neutralised refuses.

    python tools/verify_neutralisation.py

Needs a PostgreSQL server binary (`/usr/lib/postgresql/*/bin`). No network, no
root, and it never touches the host's cluster.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_mail_capture import Cluster, _bindir  # noqa: E402

from odoo_dwg import neutralise  # noqa: E402

COMMON = """
    CREATE TABLE ir_module_module (id serial PRIMARY KEY, name varchar, latest_version varchar);
    CREATE TABLE ir_model_data (id serial PRIMARY KEY, module varchar, name varchar,
                                model varchar, res_id integer);
    CREATE TABLE ir_cron (id serial PRIMARY KEY, cron_name varchar, active boolean);
    CREATE TABLE ir_config_parameter (id serial PRIMARY KEY, key varchar, value text);
    CREATE TABLE iap_account (id serial PRIMARY KEY, service_name varchar, account_token varchar);
    CREATE TABLE mail_template (id serial PRIMARY KEY, mail_server_id integer);
    CREATE TABLE delivery_carrier (id serial PRIMARY KEY, active boolean,
                                   prod_environment boolean, delivery_type varchar);
    CREATE TABLE website (id serial PRIMARY KEY, name varchar, domain varchar,
                          cdn_activated boolean);
    INSERT INTO ir_cron (cron_name, active) VALUES
      ('Autovacuum', true), ('Mail queue', true), ('Digest', true), ('Publisher', true),
      ('Sync', true), ('Backup', true), ('Already off', false), ('Queue vacuum', true);
    INSERT INTO ir_model_data (module, name, model, res_id) VALUES
      ('base', 'autovacuum_job', 'ir.cron', 1), ('mail', 'ir_cron_mail_scheduler_action',
      'ir.cron', 2), ('queue_job', 'ir_cron_autovacuum_queue_jobs', 'ir.cron', 8);
    INSERT INTO ir_config_parameter (key, value) VALUES
      ('web.base.url', 'https://erp.client.example'), ('web.base.url.freeze', 'True'),
      ('database.uuid', '11111111-2222-3333-4444-555555555555');
    INSERT INTO iap_account (service_name, account_token) VALUES ('sms', 'abc123');
    INSERT INTO mail_template (mail_server_id) VALUES (7), (NULL);
    INSERT INTO delivery_carrier (active, prod_environment, delivery_type) VALUES
      (true, true, 'fixed'), (true, true, 'dhl');
    INSERT INTO website (name, domain, cdn_activated) VALUES ('Shop', 'shop.client.example', true);
"""

SCHEMAS: dict[str, str] = {
    "12.0-era": COMMON + """
        INSERT INTO ir_module_module (name, latest_version) VALUES ('base', '12.0.1.3');
        CREATE TABLE queue_job (id serial PRIMARY KEY, name varchar, state varchar);
        CREATE TABLE res_company (id serial PRIMARY KEY, name varchar, sii_enabled boolean,
                                  sii_test boolean);
        CREATE TABLE payment_acquirer (id serial PRIMARY KEY, provider varchar,
                                       environment varchar, website_published boolean);
        CREATE TABLE res_users (id serial PRIMARY KEY, login varchar,
                                google_calendar_rtoken varchar, google_calendar_token varchar);
        INSERT INTO queue_job (name, state) VALUES ('send invoice', 'pending'),
                                                   ('old', 'done');
        INSERT INTO res_company (name, sii_enabled, sii_test) VALUES ('ACME', true, false);
        INSERT INTO payment_acquirer (provider, environment) VALUES ('stripe', 'prod'),
                                                                    ('transfer', 'test');
        INSERT INTO res_users (login, google_calendar_rtoken, google_calendar_token) VALUES
          ('admin', 'r-tok', 'tok'), ('demo', NULL, NULL);
    """,
    "14.0-era": COMMON + """
        INSERT INTO ir_module_module (name, latest_version) VALUES ('base', '14.0.1.3');
        CREATE TABLE res_company (id serial PRIMARY KEY, name varchar,
                                  l10n_es_edi_test_env boolean, tbai_enabled boolean,
                                  tbai_test_enabled boolean, verifactu_test boolean);
        CREATE TABLE account_edi_proxy_client_user (id serial PRIMARY KEY, proxy_type varchar);
        CREATE TABLE res_users (id serial PRIMARY KEY, login varchar,
                                google_calendar_rtoken varchar, google_calendar_token varchar,
                                microsoft_calendar_token varchar, microsoft_calendar_rtoken varchar);
        CREATE TABLE mail_message (id serial PRIMARY KEY, mail_server_id integer);
        CREATE TABLE mail_mail (id serial PRIMARY KEY, mail_message_id integer, state varchar);
        INSERT INTO res_company (name, l10n_es_edi_test_env, tbai_enabled, tbai_test_enabled,
                                 verifactu_test) VALUES
          ('ACME', false, true, false, false), ('Off', false, false, false, NULL);
        INSERT INTO account_edi_proxy_client_user (proxy_type) VALUES ('l10n_it_edi');
        INSERT INTO res_users (login, google_calendar_rtoken, microsoft_calendar_token) VALUES
          ('admin', 'r-tok', 'ms-tok');
        INSERT INTO mail_message (mail_server_id) VALUES (3), (3), (3), (NULL);
        INSERT INTO mail_mail (mail_message_id, state) VALUES
          (1, 'outgoing'), (2, 'sent'), (3, 'exception'), (4, 'outgoing');
    """,
    "16.0-era": COMMON + """
        INSERT INTO ir_module_module (name, latest_version) VALUES ('base', '16.0.1.3');
        INSERT INTO ir_config_parameter (key, value) VALUES
          ('account_edi_proxy_client.demo', 'prod');
        CREATE TABLE res_company (id serial PRIMARY KEY, name varchar,
                                  l10n_es_edi_test_env boolean);
        CREATE TABLE account_edi_proxy_client_user (id serial PRIMARY KEY, proxy_type varchar);
        CREATE TABLE res_users (id serial PRIMARY KEY, login varchar,
                                microsoft_calendar_token varchar, microsoft_calendar_rtoken varchar,
                                microsoft_synchronization_stopped boolean);
        CREATE TABLE google_calendar_credentials (id serial PRIMARY KEY, calendar_rtoken varchar,
                                                  calendar_token varchar,
                                                  synchronization_stopped boolean);
        INSERT INTO res_company (name, l10n_es_edi_test_env) VALUES ('ACME', false);
        INSERT INTO account_edi_proxy_client_user (proxy_type) VALUES ('l10n_it_edi');
        INSERT INTO res_users (login, microsoft_calendar_token, microsoft_synchronization_stopped)
          VALUES ('admin', 'ms-tok', false), ('demo', NULL, NULL);
        INSERT INTO google_calendar_credentials (calendar_rtoken, calendar_token,
                                                 synchronization_stopped) VALUES
          ('r-tok', 'tok', false), (NULL, NULL, false);
    """,
    "17.0-era": COMMON + """
        INSERT INTO ir_module_module (name, latest_version) VALUES ('base', '17.0.1.3');
        INSERT INTO ir_config_parameter (key, value) VALUES
          ('mail.web_push_vapid_private_key', 'priv'), ('mail.web_push_vapid_public_key', 'pub'),
          ('mail.sfu_server_key', 'sfu');
        CREATE TABLE res_company (id serial PRIMARY KEY, name varchar,
                                  l10n_es_edi_test_env boolean,
                                  l10n_es_edi_verifactu_test_environment boolean,
                                  l10n_my_edi_mode varchar);
        CREATE TABLE account_edi_proxy_client_user (id serial PRIMARY KEY, proxy_type varchar,
                                                    edi_mode varchar, active boolean);
        CREATE TABLE microsoft_calendar_credentials (id serial PRIMARY KEY,
                                                     calendar_sync_token varchar,
                                                     synchronization_stopped boolean);
        CREATE TABLE mail_partner_device (id serial PRIMARY KEY, endpoint varchar);
        INSERT INTO res_company (name, l10n_es_edi_test_env,
                                 l10n_es_edi_verifactu_test_environment, l10n_my_edi_mode) VALUES
          ('ACME', false, false, 'prod');
        INSERT INTO account_edi_proxy_client_user (proxy_type, edi_mode, active) VALUES
          ('peppol', 'prod', true), ('l10n_my_edi', 'prod', true);
        INSERT INTO microsoft_calendar_credentials (calendar_sync_token, synchronization_stopped)
          VALUES ('sync', false);
        INSERT INTO mail_partner_device (endpoint) VALUES ('https://push.example/abc');
    """,
    "18.0-era": COMMON + """
        INSERT INTO ir_module_module (name, latest_version) VALUES ('base', '18.0.1.3');
        INSERT INTO ir_config_parameter (key, value) VALUES
          ('cloud_storage_provider', 'azure'), ('cloud_storage_azure_client_secret', 's3cret'),
          ('cloud_storage_google_account_info', '{}');
        -- 18.0's service_name is not stored; a dropped column is not a column.
        ALTER TABLE iap_account DROP COLUMN service_name;
        INSERT INTO iap_account (account_token) VALUES (repeat('x', 40));
        CREATE TABLE certificate_certificate (id serial PRIMARY KEY, name varchar,
                                              pkcs12_password varchar);
        CREATE TABLE certificate_key (id serial PRIMARY KEY, name varchar, password varchar);
        CREATE TABLE mail_push_device (id serial PRIMARY KEY, endpoint varchar);
        INSERT INTO certificate_certificate (name, pkcs12_password) VALUES ('FNMT', 'p12');
        INSERT INTO certificate_key (name, password) VALUES ('key', 'kp');
        INSERT INTO mail_push_device (endpoint) VALUES ('https://push.example/abc');
        CREATE TABLE res_company (id serial PRIMARY KEY, name varchar, sii_enabled boolean,
                                  sii_test boolean, l10n_es_sii_test_env boolean,
                                  l10n_es_tbai_test_env boolean,
                                  l10n_es_edi_verifactu_test_environment boolean,
                                  verifactu_test boolean, l10n_gr_edi_test_env boolean,
                                  l10n_my_edi_mode varchar, sms_twilio_auth_token varchar);
        CREATE TABLE payment_provider (id serial PRIMARY KEY, code varchar, state varchar);
        CREATE TABLE auth_oauth_provider (id serial PRIMARY KEY, enabled boolean);
        CREATE TABLE ir_act_server (id serial PRIMARY KEY, name varchar, state varchar,
                                    webhook_url varchar);
        CREATE TABLE account_edi_proxy_client_user (id serial PRIMARY KEY, proxy_type varchar,
                                                    edi_mode varchar, active boolean);
        INSERT INTO res_company (name, sii_enabled, sii_test, l10n_es_sii_test_env,
                                 l10n_es_tbai_test_env, l10n_es_edi_verifactu_test_environment,
                                 verifactu_test, l10n_gr_edi_test_env, l10n_my_edi_mode,
                                 sms_twilio_auth_token) VALUES
          ('ACME', true, false, false, false, false, false, false, 'prod', 'tw');
        INSERT INTO payment_provider (code, state) VALUES ('stripe', 'enabled'),
                                                          ('demo', 'test');
        INSERT INTO auth_oauth_provider (enabled) VALUES (true);
        INSERT INTO ir_act_server (name, state, webhook_url) VALUES
          ('Notify ERP', 'webhook', 'https://hooks.client.example/x'), ('Code', 'code', NULL);
        INSERT INTO account_edi_proxy_client_user (proxy_type, edi_mode, active) VALUES
          ('peppol', 'prod', true), ('l10n_my_edi', 'prod', true), ('l10n_gr_edi', 'prod', true);
    """,
}

#: Per era, the rules its fixture arms: each must be seen, and then be quiet.
EXPECTED: dict[str, set[str]] = {
    "12.0-era": {"sii-oca", "google-calendar-users", "queued-jobs"},
    "14.0-era": {"spain-edi-odoo", "ticketbai-oca", "verifactu-oca", "edi-proxy-demo",
                 "google-calendar-users", "microsoft-calendar-users", "queued-mail-server"},
    "16.0-era": {"spain-edi-odoo", "edi-proxy-demo", "microsoft-calendar-users",
                 "microsoft-calendar-stopped", "google-calendar-credentials"},
    "17.0-era": {"spain-edi-odoo", "verifactu-odoo", "my-edi-mode", "edi-proxy", "edi-proxy-my-gr",
                 "microsoft-calendar-credentials", "push-devices-17", "web-push-keys"},
    "18.0-era": {"sii-odoo", "ticketbai", "verifactu-odoo", "verifactu-oca", "gr-edi",
                 "my-edi-mode", "edi-proxy", "edi-proxy-my-gr", "cloud-storage",
                 "certificate-password", "certificate-key-password", "sms-twilio", "push-devices",
                 "iap"},
}

#: After neutralising, per era, a query and the value it must return.
AFTER: dict[str, list[tuple[str, str]]] = {
    "14.0-era": [
        ("SELECT value FROM ir_config_parameter WHERE key = 'account_edi_proxy_client.demo'",
         "true"),
        # Only mail still to be sent forgets its server; what was sent keeps it.
        ("SELECT string_agg(coalesce(mail_server_id::text, '-'), ',' ORDER BY id) "
         "FROM mail_message", "-,3,-,-"),
        ("SELECT string_agg(tbai_test_enabled::text, ',' ORDER BY id) FROM res_company",
         "true,false"),
    ],
    "16.0-era": [
        ("SELECT value FROM ir_config_parameter WHERE key = 'account_edi_proxy_client.demo'",
         "true"),
    ],
    "17.0-era": [
        ("SELECT endpoint FROM mail_partner_device", neutralise.PUSH_SINK),
        ("SELECT string_agg(value, ',' ORDER BY id) FROM ir_config_parameter "
         "WHERE key LIKE 'mail.%'", ",,"),
        ("SELECT count(*) FROM ir_config_parameter WHERE key = 'account_edi_proxy_client.demo'",
         "0"),
    ],
    "18.0-era": [
        # A short token keeps its prefix; a long one is replaced whole, as 17.0+ do.
        ("SELECT string_agg(account_token, ',' ORDER BY id) FROM iap_account",
         "abc123+disabled,dummy_value+disabled"),
        ("SELECT endpoint FROM mail_push_device", neutralise.PUSH_SINK),
        ("SELECT string_agg(active::text, ',' ORDER BY id) FROM account_edi_proxy_client_user",
         "true,false,false"),
        ("SELECT pkcs12_password FROM certificate_certificate", "dummy"),
    ],
}

def _snapshot(cluster: Cluster, db: str, tables: list[str]) -> dict[str, str]:
    return {table: cluster.value(
        f"SELECT coalesce(string_agg(to_jsonb(t)::text, E'\\n' ORDER BY t.id), '') "
        f"FROM {table} t", db) for table in tables}


def _armed(cluster: Cluster, db: str) -> dict[str, int]:
    existing = {tuple(line.split("\t")) for line in
                cluster.value(neutralise.columns_sql(), db).splitlines() if line}
    rules = neutralise.applicable(existing)
    rows = [line.split("\t") for line in
            cluster.value(neutralise.check_sql(rules), db).splitlines() if line]
    return {armed.rule: armed.count for armed in neutralise.read_armed(rows)}


def main() -> int:
    bindir = _bindir()
    if bindir is None:
        print("No PostgreSQL server binaries found under /usr/lib/postgresql.")
        return 1
    failures: list[str] = []

    def check(label: str, condition: bool, detail: object = "") -> None:
        print(f"{'ok  ' if condition else 'FAIL'}  {label}")
        if not condition:
            failures.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory(prefix="odwg-neutral-") as tmp:
        cluster = Cluster(Path(tmp), bindir)
        cluster.start()
        try:
            for index, (label, schema) in enumerate(SCHEMAS.items()):
                db = f"probe{index}"
                cluster.sql(f"CREATE DATABASE {db}")
                if (setup := cluster.sql(schema, db)).returncode != 0:
                    raise SystemExit(f"fixture failed: {setup.stderr.strip()}")
                tables = [t for t in cluster.value(
                    "SELECT string_agg(tablename, ' ' ORDER BY tablename) FROM pg_tables "
                    "WHERE schemaname = 'public'", db).split() if t != "ir_module_module"]
                before = _snapshot(cluster, db, tables)

                armed = _armed(cluster, db)
                check(f"{label}: the check sees a production copy as armed",
                      armed.get("crons") == 5 and "base-url" in armed, armed)
                check(f"{label}: the check sees every rule the fixture arms",
                      EXPECTED.get(label, set()) <= set(armed),
                      EXPECTED.get(label, set()) - set(armed))
                guard = cluster.sql(neutralise.guard_sql(), db)
                check(f"{label}: the scripts' guard refuses a production copy, naming it",
                      guard.returncode != 0 and "crons (5)" in guard.stderr, guard.stderr.strip())

                refused = cluster.sql(neutralise.restore_sql(), db)
                check(f"{label}: restore refuses a database never neutralised",
                      refused.returncode != 0 and "no neutralisation" in refused.stderr,
                      refused.stderr.strip())

                applied = cluster.sql(neutralise.apply_sql(), db)
                check(f"{label}: neutralise runs", applied.returncode == 0, applied.stderr.strip())
                check(f"{label}: nothing can act afterwards", _armed(cluster, db) == {},
                      _armed(cluster, db))
                guard = cluster.sql(neutralise.guard_sql(), db)
                check(f"{label}: the scripts' guard lets a neutralised copy through",
                      guard.returncode == 0, guard.stderr.strip())
                check(f"{label}: housekeeping crons stay active",
                      cluster.value("SELECT string_agg(id::text, ',' ORDER BY id) FROM ir_cron "
                                    "WHERE active", db) == "1,8")
                uuid = cluster.value("SELECT value FROM ir_config_parameter WHERE key = "
                                     "'database.uuid'", db)
                check(f"{label}: the copy has its own uuid",
                      uuid != "11111111-2222-3333-4444-555555555555" and len(uuid) == 36, uuid)
                check(f"{label}: links point at the local instance",
                      cluster.value("SELECT value FROM ir_config_parameter WHERE key = "
                                    "'web.base.url'", db) == neutralise.DEFAULT_LOCAL_URL)
                for query, expected in AFTER.get(label, []):
                    got = cluster.value(query, db)
                    check(f"{label}: {query[:70]}… = {expected!r}", got == expected, got)

                # What a module update and a migration step do on their own.
                cluster.value("UPDATE ir_cron SET active = true WHERE id = 3; "
                              "INSERT INTO ir_cron (cron_name, active) VALUES ('New in 13', true);"
                              " SELECT 1", db)
                again = cluster.sql(neutralise.apply_sql(), db)
                check(f"{label}: re-applying runs", again.returncode == 0, again.stderr.strip())
                check(f"{label}: a cron switched back on, and a new one, are off again",
                      _armed(cluster, db) == {}, _armed(cluster, db))
                check(f"{label}: re-applying kept production's first record and uuid",
                      cluster.value(f"SELECT original::text || run::text FROM "
                                    f"{neutralise.RECORD_TABLE} WHERE relation = 'ir_cron' AND "
                                    "row_id = 3", db) == "true1"
                      and cluster.value("SELECT value FROM ir_config_parameter WHERE key = "
                                        "'database.uuid'", db) == uuid)

                restored = cluster.sql(neutralise.restore_sql(), db)
                check(f"{label}: restore runs", restored.returncode == 0, restored.stderr.strip())
                check(f"{label}: restore names the cron production never had",
                      "left neutralised, not in production" in restored.stderr
                      and "ir_cron row 9" in restored.stderr, restored.stderr.strip())
                after = _snapshot(cluster, db, tables)
                cron_after = after.pop("ir_cron").splitlines()
                cron_before = before.pop("ir_cron").splitlines()
                check(f"{label}: production's crons are back as they were",
                      cron_after[:8] == cron_before
                      and '"active": false' in cron_after[8], cron_after)
                check(f"{label}: every other row is back, column for column",
                      after == before, {k: (before[k], after[k]) for k in before
                                        if before[k] != after[k]})
                check(f"{label}: restore leaves no table of ours",
                      cluster.value("SELECT count(*) FROM pg_tables WHERE tablename LIKE "
                                    "'odwg_neutralisation%'", db) == "0")
        finally:
            cluster.stop()

    if failures:
        print(f"\n{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nNeutralisation is applied, repeatable and given back exactly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
