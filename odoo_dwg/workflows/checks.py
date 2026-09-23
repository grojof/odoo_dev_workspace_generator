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

import json
from datetime import date

from .. import egress
from .. import findings as fl
from ..i18n import t, tf
from ..models import DB_NAME_RE, MigrationEnv
from ..system import read_dir_files, read_text
from ..ui import level_text
from . import findings, migration
from .common import armed_state, mail_state, report_armed, report_mail_state

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


def neutralise_check(database: str, host: str, port: int, user: str) -> int:
    """Whether anything in a database can still act on the outside."""
    if not DB_NAME_RE.fullmatch(database):
        print(level_text("ERROR", tf("Invalid database name: {}", database)))
        return UNKNOWN
    armed = armed_state(database, host, port, user)
    mail = mail_state(database, host, port, user)
    if armed is None or mail is None:
        return UNKNOWN
    if report_armed(database, armed, mail):
        print(level_text("INFO", t(
            "Nothing was changed. Menu -> Migration (or a workspace) -> Neutralise a database "
            "turns it off.")))
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


def _findings_ledger(source: str, target: str):
    env = _environment(source, target)
    if env is None:
        return None, None
    return env, findings.load_ledger(env)


def findings_list(source: str, target: str) -> int:
    """The findings, one line each. Non-zero while any decision is still pending."""
    env, ledger = _findings_ledger(source, target)
    if ledger is None:
        return CLEAN if env is not None and not env.findings_ledger.exists() else UNKNOWN
    findings.print_findings(ledger)
    waiting = fl.pending(ledger)
    if waiting:
        print(level_text("INFO", tf(
            "{} finding(s) await a decision. Menu -> Migration -> Findings -> Record a "
            "decision records one.", str(len(waiting)))))
        return FOUND
    return CLEAN


def findings_show(source: str, target: str, finding_id: str) -> int:
    """One finding in full, as the ledger holds it."""
    _env, ledger = _findings_ledger(source, target)
    if ledger is None:
        return UNKNOWN
    for finding in ledger.findings:
        if finding.id == finding_id:
            print(json.dumps(fl.finding_json(finding), indent=2, ensure_ascii=False))
            return CLEAN
    print(level_text("ERROR", tf("No finding {} in the ledger.", finding_id)))
    return UNKNOWN


def findings_validate(source: str, target: str) -> int:
    """Whether the ledger is one the tool accepts; every problem named if not."""
    env = _environment(source, target)
    if env is None:
        return UNKNOWN
    if not env.findings_ledger.exists():
        print(level_text("INFO", tf("No findings ledger yet in {}.", str(env.findings_ledger))))
        return UNKNOWN
    if findings.load_ledger(env) is None:
        return FOUND
    print(level_text("OK", tf("{} is valid.", str(env.findings_ledger))))
    return CLEAN


def findings_report(source: str, target: str, kind: str, lang: str) -> int:
    """A report rendered to stdout. The menu action is the one that writes it to disk."""
    env, ledger = _findings_ledger(source, target)
    if env is None or ledger is None:
        return UNKNOWN
    try:
        print(findings.render(env, ledger, kind, lang, date.today()), end="")
    except fl.LedgerError as error:
        print(level_text("ERROR", t("No report was rendered:")))
        for problem in error.problems:
            print(f"  - {problem}")
        return UNKNOWN
    return CLEAN


def findings_links(source: str, target: str) -> int:
    """Every URL in the ledger, requested; the ones that do not answer are named."""
    _env, ledger = _findings_ledger(source, target)
    if ledger is None:
        return UNKNOWN
    broken = findings.broken_links(ledger)
    if not broken:
        print(level_text("OK", tf("{} link(s) answer.", str(len(fl.ledger_urls(ledger))))))
        return CLEAN
    for where, url, answer in broken:
        print(f"  {answer:<8} {url}  ({where})")
    return FOUND
