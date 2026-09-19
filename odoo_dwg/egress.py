"""Outbound control (OpenSnitch) and mail capture (Mailpit) — pure facts and builders.

No I/O: the planners turn these into commands, ``system`` probes the host. Every
default below was measured on the reference host (WSL Ubuntu 24.04, 2026-09-19);
``openspec/changes/archive/*-add-egress-control/design.md`` records why each one
differs from what the upstream packages ship, and ``docs/egress-control.md`` how
to update the pinned versions.
"""

from __future__ import annotations

import json
import re

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
              "Odoo (odoo-bin: workspaces, migrations, shell) may reach localhost only.",
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


def mail_redirect_sql() -> str:
    """Point every mail server of a database at Mailpit and stop fetching mail.

    Column- and table-aware so it runs on Odoo 12–19: ``smtp_authentication``
    appeared in later versions and ``fetchmail_server`` exists only with its module.
    Meant for rehearsal copies — never for a database going back to production."""
    return (
        "DO $$ BEGIN "
        "UPDATE ir_mail_server SET "
        f"smtp_host = '{MAILPIT_SMTP_HOST}', smtp_port = {MAILPIT_SMTP_PORT}, "
        "smtp_encryption = 'none', smtp_user = NULL, smtp_pass = NULL; "
        "IF EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'ir_mail_server' AND column_name = 'smtp_authentication') THEN "
        "UPDATE ir_mail_server SET smtp_authentication = 'login'; END IF; "
        "IF to_regclass('fetchmail_server') IS NOT NULL THEN "
        "UPDATE fetchmail_server SET active = false; END IF; "
        "END $$;"
    )
