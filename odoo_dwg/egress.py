"""Outbound control (OpenSnitch) and mail capture (Mailpit) — pure facts and builders.

No I/O: the planners turn these into commands, ``system`` probes the host. Every
default below was measured on the reference host (WSL Ubuntu 24.04, 2026-09-19);
``openspec/changes/archive/*-add-egress-control/design.md`` records why each one
differs from what the upstream packages ship, and ``docs/host/egress-control.md`` how
to update the pinned versions.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# --- pinned upstream releases -------------------------------------------------

# OpenSnitch from its GitHub release, not Ubuntu's archive (1.5.8 in noble). The
# SHA-512 values come from the release's readme.txt.asc, signed by the maintainer
# (Gustavo Iñiguez Goya, EdDSA key 858F918F2887BD809F08DDDB6CD595FEFD12DAE2).
OPENSNITCH_VERSION = "1.8.0"
OPENSNITCH_SIGNING_KEY = "858F918F2887BD809F08DDDB6CD595FEFD12DAE2"
OPENSNITCH_BASE_URL = "https://github.com/evilsocket/opensnitch/releases/download/v1.8.0"
OPENSNITCH_PACKAGES: tuple[tuple[str, str], ...] = (
    ("opensnitch_1.8.0-1_amd64.deb",
     "a0c9a2aaddac31dd5cf847212df1814ea2115a12be07558f78e48c8cf95c5da3"
     "ab2ab4c94e0367215e452cd8c4c1846270c600614f09f12a390cbf474e07ee0d"),
    ("python3-opensnitch-ui_1.8.0-1_all.deb",
     "e43ec7993f95c7babe7e59b44d054c6454da15a9c4dec66faa543a079b7e4a09"
     "7ecf6b14a0e705c1f229a627c528287229bc62cfd00bd7f91853bf40250db4ce"),
)

# Mailpit publishes no checksum file and no attestation; the SHA-256 is the digest
# GitHub records for the release asset (API: assets[].digest).
MAILPIT_VERSION = "1.31.2"
MAILPIT_URL = (
    "https://github.com/axllent/mailpit/releases/download/v1.31.2/mailpit-linux-amd64.tar.gz"
)
MAILPIT_SHA256 = "397a14cad03ae34d7c5f13215fd24971fed5ce48bf4237554829b0a10d4306ad"
MAILPIT_BINARY = "/usr/local/bin/mailpit"
MAILPIT_UNIT = "/etc/systemd/system/mailpit.service"
# Captured mail survives restarts; Mailpit prunes to its default message limit.
MAILPIT_DATABASE = "/var/lib/mailpit/mailpit.db"
MAILPIT_SMTP_HOST = "127.0.0.1"
MAILPIT_SMTP_PORT = 1025
MAILPIT_UI_PORT = 8025

# --- OpenSnitch daemon --------------------------------------------------------

OPENSNITCH_CONFIG = "/etc/opensnitchd/default-config.json"
OPENSNITCH_RULES_DIR = "/etc/opensnitchd/rules"
# Rules the tool owns carry this prefix; nothing else in the rules directory is touched.
# OpenSnitch evaluates rules in file-name order and the first match decides, so the
# prefix sorts ahead of everything else ("-" < digits < letters): rules made from
# the UI ("allow-always-…", "deny-…") and the package's "000-…" can never pre-empt
# the Odoo rule. An operator rule meant to win must be named to sort even earlier.
RULE_PREFIX = "00-odwg-"

# Keys the tool sets in the shipped config, as dotted paths; every other key stays
# as the package ships it.
HARDENED_SETTINGS: dict[str, object] = {
    # The daemon's own action applies whenever the UI is not connected. The
    # package ships "allow", which lets everything without a rule out.
    "DefaultAction": "deny",
    # With "ebpf", a process lost its identity after about a minute and a rule on
    # its command line stopped matching; "proc" held. Odoo runs for hours.
    "ProcMonitorMethod": "proc",
    # A connection whose process cannot be found skips every rule and gets the
    # default action, unlogged, while this is false. WSL's localhost relay (a
    # Windows browser opening Mailpit's UI) is such a connection: with "true" it
    # is matched by the localhost rule, and any other process-less connection is
    # denied and logged instead of silently dropped.
    "InterceptUnknown": True,
    # "true" would cut every open connection (editor, remote session) on start.
    "Internal.FlushConnsOnStart": False,
    # "true" lets packets through when the daemon is not reading the queue: fail
    # open. "false" fails closed; a clean `systemctl stop` still restores traffic.
    "FwOptions.QueueBypass": False,
    "LogLevel": 2,
    # Every connection decision to the system journal, with or without the UI:
    # the only record that survives a closed window (`journalctl -t opensnitch`).
    # 1.8.0 always tags these "opensnitch" (its Tag key is not used by the syslog
    # logger) and offers rfc5424 or csv, not json, for syslog.
    "Server.Loggers": [{"Name": "syslog", "Format": "rfc5424"}],
}

#: The syslog tag 1.8.0 writes its decisions under — the name to ask the journal
#: for, stated here once so a reader and this configuration cannot drift apart.
OPENSNITCH_JOURNAL_TAG = "opensnitch"

# Hosts any process may reach: the development flow (git, gh, pip, uv, apt, npm,
# Odoo/OCA clones, release downloads). Odoo never gets here: its rule comes first.
DEV_INFRASTRUCTURE_HOSTS: tuple[str, ...] = (
    r"github\.com",
    r"cli\.github\.com",
    r"api\.github\.com",
    r"codeload\.github\.com",
    r"uploads\.github\.com",
    r"[a-z0-9-]+\.githubusercontent\.com",
    r"pypi\.org",
    r"files\.pythonhosted\.org",
    r"([a-z0-9-]+\.)*astral\.sh",
    # The archive and its country mirrors (es.archive.ubuntu.com, …).
    r"([a-z]{2}\.)?archive\.ubuntu\.com",
    r"security\.ubuntu\.com",
    r"registry\.npmjs\.org",
)

_RULE_STAMP = "2026-09-19T00:00:00Z"


def _rule(name: str, description: str, action: str, operator: dict) -> dict:
    return {
        "created": _RULE_STAMP,
        "updated": _RULE_STAMP,
        "name": f"{RULE_PREFIX}{name}",
        "description": description,
        "action": action,
        "duration": "always",
        "operator": operator,
        "enabled": True,
        # The first matching rule decides; the file names fix the order.
        "precedence": True,
        "nolog": False,
    }


def _op(operand: str, data: str, kind: str = "simple") -> dict:
    return {"operand": operand, "data": data, "type": kind, "list": [], "sensitive": False}


def baseline_rules(resolvers: list[str]) -> list[dict]:
    """The owned rule set, in evaluation order. ``resolvers`` are the host's
    non-loopback DNS servers (from /etc/resolv.conf)."""
    rules = [
        # A "list" operator ANDs its items, so IPv4 and IPv6 loopback are two rules.
        _rule("000-allow-localhost", "IPv4 loopback: PostgreSQL, Mailpit, local services.",
              "allow", _op("dest.network", "127.0.0.0/8", "network")),
        _rule("000-allow-localhost6", "IPv6 loopback.", "allow", _op("dest.ip", "::1")),
        _rule("001-allow-systemd-resolved", "The system DNS resolver.", "allow",
              _op("process.path", "/usr/lib/systemd/systemd-resolved")),
    ]
    if resolvers:
        pattern = "^(" + "|".join(re.escape(ip) for ip in resolvers) + ")$"
        rules.append(
            # A "list" operator ANDs its items: the resolver addresses *and* the
            # DNS port. Without the port this would open every port of the
            # resolver — on WSL, the Windows host — to every process, Odoo
            # included.
            _rule("001-allow-dns-resolvers", "DNS servers from /etc/resolv.conf, port 53 only.",
                  "allow",
                  {"operand": "list", "data": "", "type": "list", "sensitive": False,
                   "list": [_op("dest.ip", pattern, "regexp"), _op("dest.port", "53")]})
        )
    rules += [
        _rule("002-allow-ntp", "System clock synchronisation.", "allow",
              _op("process.path", "/usr/lib/systemd/systemd-timesyncd")),
        # Ahead of every allow rule but loopback and DNS: rules are evaluated in
        # file-name order and the first match wins, so an allow that matched
        # odoo-bin first (the VS Code server's own processes, for instance) would
        # open exactly the hole this rule exists to close.
        _rule("003-reject-odoo-external",
              "Odoo (odoo-bin: workspaces, migrations, shell) may reach localhost only — "
              "DNS on port 53 is allowed by the rules above.",
              "reject", _op("process.command", "odoo-bin", "regexp")),
        _rule("004-allow-vscode-server", "The VS Code server of any user (WSL / remote).", "allow",
              _op("process.path", r"^/home/[^/]+/\.vscode-server/", "regexp")),
        _rule("020-allow-dev-infrastructure",
              "Development infrastructure any tool may reach. Odoo is rejected by 003 first.",
              "allow",
              _op("dest.host", "^(" + "|".join(DEV_INFRASTRUCTURE_HOSTS) + ")$", "regexp")),
    ]
    return rules


def rule_filename(rule: dict) -> str:
    return f"{rule['name']}.json"


def render_rule(rule: dict) -> str:
    return json.dumps(rule, indent=2) + "\n"


def parse_resolvers(resolv_conf: str) -> list[str]:
    """Non-loopback ``nameserver`` addresses, in file order, without duplicates."""
    found: list[str] = []
    for line in resolv_conf.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "nameserver":
            address = parts[1]
            if address.startswith("127.") or address == "::1" or address in found:
                continue
            if re.fullmatch(r"[0-9a-fA-F:.]+", address):
                found.append(address)
    return found


def hardening_script() -> str:
    """A python3 snippet that applies ``HARDENED_SETTINGS`` to the shipped config
    in place, keeping every other key. Run as root by the plan."""
    settings = json.dumps(HARDENED_SETTINGS)
    return (
        "import json\n"
        f"path = {OPENSNITCH_CONFIG!r}\n"
        "config = json.load(open(path))\n"
        f"for dotted, value in json.loads({settings!r}).items():\n"
        "    node = config\n"
        "    *parents, key = dotted.split('.')\n"
        "    for parent in parents:\n"
        "        node = node.setdefault(parent, {})\n"
        "    node[key] = value\n"
        "import os\n"
        "tmp = path + '.odwg-tmp'\n"
        "with open(tmp, 'w') as handle:\n"
        "    json.dump(config, handle, indent=4)\n"
        "os.replace(tmp, path)  # atomic: never a truncated config\n"
    )


def config_deviations(config: dict) -> list[str]:
    """Hardened keys whose value differs in ``config`` (as ``key: actual``)."""
    deviations = []
    for dotted, wanted in HARDENED_SETTINGS.items():
        node: object = config
        for part in dotted.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if node != wanted:
            deviations.append(f"{dotted}: {node!r}")
    return deviations


# --- Mailpit ------------------------------------------------------------------


def render_mailpit_unit() -> str:
    return (
        "[Unit]\n"
        "Description=Mailpit — local SMTP capture (odoo_dwg)\n"
        "After=network.target\n"
        "\n"
        "[Service]\n"
        "DynamicUser=yes\n"
        "StateDirectory=mailpit\n"
        f"ExecStart={MAILPIT_BINARY} --smtp {MAILPIT_SMTP_HOST}:{MAILPIT_SMTP_PORT} "
        f"--listen {MAILPIT_SMTP_HOST}:{MAILPIT_UI_PORT} --database {MAILPIT_DATABASE}\n"
        "Restart=on-failure\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


#: The table capture writes its record in. No Odoo model refers to it, so nothing
#: loads it; restore drops it. It has to live in the database and not beside it,
#: because it must survive the dump and restore of every migration step.
CAPTURE_RECORD_TABLE = "odwg_mail_capture"
#: The name the added server carries in Odoo's own UI.
CAPTURE_SERVER_NAME = "Mailpit (odoo_dwg capture)"
#: Lower than any sequence Odoo's UI produces, so the capture is the one picked.
CAPTURE_SERVER_SEQUENCE = -1


def mail_capture_sql() -> str:
    """Stop a database's mail leaving, without altering what is configured.

    Odoo picks its outgoing server with an ``active``-filtered search ordered by
    ``sequence``, from 12.0 to 19.0, so deactivating the client's servers and
    adding one of our own with a lower sequence captures the mail while every
    host, user and password stays in its own column, untouched.

    The added row is *cloned* from an existing one: ``ir_mail_server`` gained
    required columns between 12.0 and 19.0 (``smtp_authentication`` among them),
    and an ``INSERT`` naming columns has to be right for eight schemas.
    ``jsonb_populate_record`` against the table's own row type inherits whatever
    columns that version has, already satisfying their constraints.
    """
    return (
        f"CREATE TABLE IF NOT EXISTS {CAPTURE_RECORD_TABLE} ("
        "relation text NOT NULL, row_id integer NOT NULL, role text NOT NULL, "
        "captured_at timestamptz NOT NULL DEFAULT now(), "
        "PRIMARY KEY (relation, row_id)); "
        "DO $$ BEGIN "
        # Recorded before anything is switched off, or there is nothing to observe.
        f"INSERT INTO {CAPTURE_RECORD_TABLE} (relation, row_id, role) "
        "SELECT 'ir_mail_server', id, 'deactivated' FROM ir_mail_server WHERE active "
        f"AND id NOT IN (SELECT row_id FROM {CAPTURE_RECORD_TABLE} "
        "WHERE relation = 'ir_mail_server') ON CONFLICT DO NOTHING; "
        # Never our own server: without this, a second capture switches off the
        # only thing keeping the mail in.
        "UPDATE ir_mail_server SET active = false WHERE active "
        f"AND id NOT IN (SELECT row_id FROM {CAPTURE_RECORD_TABLE} "
        "WHERE relation = 'ir_mail_server' AND role = 'added'); "
        "UPDATE ir_mail_server SET active = true WHERE NOT active "
        f"AND id IN (SELECT row_id FROM {CAPTURE_RECORD_TABLE} "
        "WHERE relation = 'ir_mail_server' AND role = 'added'); "
        f"IF NOT EXISTS (SELECT 1 FROM {CAPTURE_RECORD_TABLE} "
        "WHERE relation = 'ir_mail_server' AND role = 'added') THEN "
        # No row to clone means no mail server at all, and Odoo already falls back
        # to the configuration file. Nothing is added, and the check says so.
        "WITH added AS (INSERT INTO ir_mail_server "
        "SELECT (jsonb_populate_record(NULL::ir_mail_server, to_jsonb(src) || jsonb_build_object("
        "'id', nextval(pg_get_serial_sequence('ir_mail_server', 'id')), "
        f"'name', '{CAPTURE_SERVER_NAME}', "
        f"'smtp_host', '{MAILPIT_SMTP_HOST}', 'smtp_port', {MAILPIT_SMTP_PORT}, "
        "'smtp_encryption', 'none', 'smtp_user', NULL, 'smtp_pass', NULL, "
        f"'sequence', {CAPTURE_SERVER_SEQUENCE}, 'active', true))).* "
        "FROM (SELECT * FROM ir_mail_server ORDER BY id LIMIT 1) src RETURNING id) "
        f"INSERT INTO {CAPTURE_RECORD_TABLE} (relation, row_id, role) "
        "SELECT 'ir_mail_server', id, 'added' FROM added; END IF; "
        "IF to_regclass('fetchmail_server') IS NOT NULL THEN "
        f"INSERT INTO {CAPTURE_RECORD_TABLE} (relation, row_id, role) "
        "SELECT 'fetchmail_server', id, 'deactivated' FROM fetchmail_server WHERE active "
        "ON CONFLICT DO NOTHING; "
        "UPDATE fetchmail_server SET active = false WHERE active; END IF; "
        "END $$;"
    )


def mail_restore_sql() -> str:
    """Give a captured database back the mail configuration it had.

    Only the rows capture recorded: a mail server the client had switched off
    before the capture stays off. A recorded row that no longer exists is raised
    as a notice rather than passed over — a mail server a migration removed is a
    difference between the database that was captured and the one handed back.
    """
    return (
        "DO $$ DECLARE missing integer; BEGIN "
        f"IF to_regclass('{CAPTURE_RECORD_TABLE}') IS NULL THEN "
        "RAISE EXCEPTION 'no mail capture is recorded in this database'; END IF; "
        "DELETE FROM ir_mail_server WHERE id IN "
        f"(SELECT row_id FROM {CAPTURE_RECORD_TABLE} "
        "WHERE relation = 'ir_mail_server' AND role = 'added'); "
        "UPDATE ir_mail_server SET active = true WHERE id IN "
        f"(SELECT row_id FROM {CAPTURE_RECORD_TABLE} "
        "WHERE relation = 'ir_mail_server' AND role = 'deactivated'); "
        f"SELECT count(*) INTO missing FROM {CAPTURE_RECORD_TABLE} r "
        "WHERE r.relation = 'ir_mail_server' AND r.role = 'deactivated' "
        "AND NOT EXISTS (SELECT 1 FROM ir_mail_server s WHERE s.id = r.row_id); "
        "IF missing > 0 THEN RAISE NOTICE "
        "'% mail server(s) recorded by the capture no longer exist', missing; END IF; "
        "IF to_regclass('fetchmail_server') IS NOT NULL THEN "
        "UPDATE fetchmail_server SET active = true WHERE id IN "
        f"(SELECT row_id FROM {CAPTURE_RECORD_TABLE} "
        "WHERE relation = 'fetchmail_server' AND role = 'deactivated'); END IF; "
        f"DROP TABLE {CAPTURE_RECORD_TABLE}; "
        "END $$;"
    )


def mail_state_sql(*, fetchmail: bool, captured: bool) -> str:
    """Read what mail this database can send. Writes nothing.

    ``fetchmail`` and ``captured`` say which optional tables exist: a query may
    not name a table that does not, so the caller asks ``to_regclass`` first and
    the parts are composed here.
    """
    parts = [
        "SELECT 'server', id::text, coalesce(name, ''), coalesce(smtp_host, ''), "
        "smtp_port::text, active::text FROM ir_mail_server"
    ]
    if fetchmail:
        parts.append(
            "SELECT 'fetchmail', id::text, coalesce(name, ''), '', '', active::text "
            "FROM fetchmail_server"
        )
    if captured:
        parts.append(
            "SELECT 'record', row_id::text, relation, role, '', '' "
            f"FROM {CAPTURE_RECORD_TABLE}"
        )
    return " UNION ALL ".join(parts) + " ORDER BY 1, 2"


@dataclass(frozen=True)
class MailServer:
    """One row of ``ir_mail_server``, as the state query reports it."""

    id: str
    name: str
    host: str
    port: str
    active: bool

    @property
    def is_capture(self) -> bool:
        return self.host == MAILPIT_SMTP_HOST and self.port == str(MAILPIT_SMTP_PORT)


@dataclass(frozen=True)
class MailState:
    """What a database can currently do with mail."""

    servers: tuple[MailServer, ...] = ()
    fetchmail_active: int = 0
    captured: bool = False
    deactivated: int = 0

    @property
    def escaping(self) -> tuple[MailServer, ...]:
        """Active servers pointing anywhere but the capture — how mail leaves."""
        return tuple(s for s in self.servers if s.active and not s.is_capture)

    @property
    def falls_back_to_config(self) -> bool:
        """No active server at all: Odoo uses the configuration file's
        ``smtp_server``, whatever that happens to be. Not the same as captured,
        and not assumed to be the capture."""
        return not any(s.active for s in self.servers)


def read_mail_state(rows: list[list[str]]) -> MailState:
    """The state query's rows, read. Unknown kinds and short rows are ignored:
    the query is ours, but a psql that printed a notice is not worth crashing on.

    A boolean reaches here as ``true``/``false``: the query casts it to text for
    the union, and ``boolean::text`` is the word. The ``t``/``f`` an operator sees
    in psql is that client's *display* of an uncast boolean, not this."""
    servers: list[MailServer] = []
    fetchmail = 0
    captured = False
    deactivated = 0
    for row in rows:
        if len(row) < 6:
            continue
        # The columns mean different things per kind; the query fixes the order.
        kind, first, second, third, fourth, last = row[:6]
        if kind == "server":
            servers.append(
                MailServer(
                    id=first, name=second, host=third, port=fourth, active=last == "true"
                )
            )
        elif kind == "fetchmail" and last == "true":
            fetchmail += 1
        elif kind == "record":
            captured = True
            if third == "deactivated":
                deactivated += 1
    return MailState(
        servers=tuple(servers),
        fetchmail_active=fetchmail,
        captured=captured,
        deactivated=deactivated,
    )


@dataclass(frozen=True)
class RuleFinding:
    """Something about the rules directory worth an operator's attention."""

    kind: str       # "absent" | "changed" | "disabled" | "unreadable" | "sorts first"
    filename: str
    detail: str = ""


#: Worst first. A foreign rule evaluated ahead of ours is the only way the rule
#: confining Odoo can be pre-empted, so it leads; an absent or disabled rule of
#: ours is the next most consequential.
_FINDING_ORDER = ("sorts first", "absent", "disabled", "changed", "unreadable")


def audit_rules(present: dict[str, str], expected: list[dict]) -> list[RuleFinding]:
    """The rules on the host, against the rules this tool would write.

    ``present`` is every file in the rules directory as ``name -> content``.
    Nothing here changes anything: a rule the operator wrote deliberately to sort
    first is a legitimate thing to have, and only the operator knows which it is.
    """
    findings: list[RuleFinding] = []
    owned = {rule_filename(rule): rule for rule in expected}
    first_owned = min(owned, default="")
    for filename, rule in sorted(owned.items()):
        if filename not in present:
            findings.append(RuleFinding("absent", filename, "the tool would write this rule"))
            continue
        try:
            found = json.loads(present[filename])
        except (ValueError, TypeError):
            findings.append(RuleFinding("unreadable", filename, "not readable as JSON"))
            continue
        if not found.get("enabled", True):
            findings.append(RuleFinding("disabled", filename, "enabled is false"))
        # Compared as data, not as text: `indent` or key order differing is not a
        # change to what OpenSnitch does, and reporting it would train the reader
        # to ignore this check.
        if found != rule:
            findings.append(
                RuleFinding("changed", filename, "differs from what the tool would write")
            )
    for filename, content in sorted(present.items()):
        if filename in owned:
            continue
        if not filename.endswith(".json"):
            continue
        try:
            json.loads(content)
        except (ValueError, TypeError):
            findings.append(RuleFinding("unreadable", filename, "not readable as JSON"))
            continue
        if first_owned and filename < first_owned:
            findings.append(
                RuleFinding(
                    "sorts first",
                    filename,
                    f"evaluated before {first_owned}, so it can pre-empt the Odoo rule",
                )
            )
    findings.sort(key=lambda finding: (_FINDING_ORDER.index(finding.kind), finding.filename))
    return findings
