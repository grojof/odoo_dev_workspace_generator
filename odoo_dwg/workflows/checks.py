"""The read-only answers, without the menu.

Every command here writes nothing, prompts for nothing and needs no terminal, so
it can be run from a script, from a pipe, or from a second terminal while a
migration runs. Each returns an exit code carrying its verdict: 0 when it found
nothing to report, 1 when it did, 2 when it could not tell.

Anything that changes the host stays in the interactive flow behind its
confirmation phrase. A check that finds something to act on names the menu
action to use; it does not perform it.
"""

from __future__ import annotations

from .. import egress
from ..i18n import t, tf
from ..models import DB_NAME_RE, MigrationEnv
from ..system import read_dir_files, read_text
from ..ui import level_text
from . import migration
from .common import mail_state, report_mail_state

#: Found something / found nothing / could not tell. A caller that cannot reach
#: the host must not read its silence as a clean result.
FOUND, CLEAN, UNKNOWN = 1, 0, 2


def egress_check() -> int:
    """The tool's own OpenSnitch rules, as they are on the host."""
    present = read_dir_files(egress.OPENSNITCH_RULES_DIR)
    if present is None:
        print(level_text("ERROR", tf("Cannot read {}.", egress.OPENSNITCH_RULES_DIR)))
        return UNKNOWN
    resolvers = egress.parse_resolvers(read_text("/etc/resolv.conf") or "")
    findings = egress.audit_rules(present, egress.baseline_rules(resolvers))
    if not findings:
        print(level_text("OK", tf("The {} rules are as the tool wrote them.", egress.RULE_PREFIX)))
        return CLEAN
    print(level_text("WARN", tf("{} rule(s) to look at.", str(len(findings)))))
    for finding in findings:
        print(f"  {finding.kind:<12} {finding.filename}  {finding.detail}")
    print(level_text("INFO", t(
        "Nothing was changed. Menu -> Provision -> Outbound firewall and mail capture "
        "rewrites the tool's own rules; your own are yours to judge."
    )))
    return FOUND


def mail_check(database: str, host: str, port: int, user: str) -> int:
    """Whether mail can leave a database."""
    if not DB_NAME_RE.fullmatch(database):
        print(level_text("ERROR", tf("Invalid database name: {}", database)))
        return UNKNOWN
    state = mail_state(database, host, port, user)
    if state is None:
        return UNKNOWN
    report_mail_state(database, state)
    if state.escaping or state.fetchmail_active:
        print(level_text("INFO", t(
            "Menu -> Migration -> Capture a database's mail in Mailpit stops it."
        )))
        return FOUND
    return CLEAN


def _environment(source: str, target: str) -> MigrationEnv | None:
    env = MigrationEnv(source=source, target=target)
    try:
        env.validate()
    except ValueError as error:
        print(level_text("ERROR", str(error)))
        return None
    return env


def migration_report(source: str, target: str) -> int:
    """The cumulative report, to stdout. Unlike the menu action, writes no file."""
    env = _environment(source, target)
    if env is None:
        return UNKNOWN
    text = read_text(str(env.steps_file))
    if not text:
        print(level_text("INFO", tf("No run recorded yet in {}.", str(env.steps_file))))
        return UNKNOWN
    report, open_items = migration.build_report(env, text)
    print(report)
    return FOUND if open_items else CLEAN


def probe_check(source: str, target: str, database: str) -> int:
    """What each of the tester's probes found, for one database."""
    env = _environment(source, target)
    if env is None:
        return UNKNOWN
    if not DB_NAME_RE.fullmatch(database):
        print(level_text("ERROR", tf("Invalid database name: {}", database)))
        return UNKNOWN
    verdicts = migration.probe_verdicts(env, database)
    if verdicts is None:
        return UNKNOWN
    migration.report_probes(database, verdicts)
    return FOUND if any(verdict.is_finding for verdict in verdicts) else CLEAN
