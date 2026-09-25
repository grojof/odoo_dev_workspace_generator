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

from .. import audit, egress
from .. import findings as fl
from ..i18n import t, tf
from ..models import DB_NAME_RE, MigrationEnv
from ..system import psql_rows, read_dir_files, read_text
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


#: Each check's title, and what fixes a finding. The audit applies none of them.
_AUDIT_TEXT = {
    "journal-codes": (
        "Journal codes shared within a company",
        "From 15.0 unique(company_id, code) refuses them and OpenUpgrade only logs it. Menu -> "
        "Migration -> Take in a client copy -> Find journal codes the target refuses renames "
        "them on the working copy."),
    "bank-duplicates": (
        "Bank statement lines imported twice",
        "Menu -> Migration -> Take in a client copy -> Find bank statement lines imported twice "
        "writes the SQL that drops them on the working copy."),
    "bank-payments": (
        "Unreconciled bank lines matching a payment posted on the bank account",
        "From 14.0 the bank counts each twice. The client's accountant reconciles them in the "
        "source before the final copy; an equal amount is not proof."),
    "bank-closed-lines": (
        "Unreconciled bank lines of closed periods",
        "Whether to carry them is the client's accountant's decision; the bank-lines intake step "
        "lists them."),
    "constraints-missing": (
        "Declared constraints PostgreSQL does not have",
        "The data breaks them. Correct it on the working copy before the step that adds the "
        "constraint, and run the chain again."),
    "required-empty": (
        "Required fields left empty",
        "Fill them on the working copy as a data correction, or record why they may stay empty."),
    "statement-lines-reconciled": (
        "Bank statement lines stored as reconciled with a line still in suspense",
        "The driver's 14.0 repair recomputes them; a database migrated without it needs the same "
        "recompute."),
}


def _audit_query(query: str, database: str, host: str, port: int, user: str
                 ) -> list[list[str]] | None:
    return psql_rows(query, database, host, port, user)


def _run_audit(database: str, host: str, port: int, user: str,
               catalogue: audit.Catalogue) -> list[audit.Result]:
    results: list[audit.Result] = []
    duplicates: set[int] = set()
    for check in audit.CHECKS:
        if not audit.applies(check, catalogue):
            results.append(audit.Result(check, audit.NOT_APPLICABLE))
            continue
        rows = _audit_query(audit.QUERIES[check], database, host, port, user)
        if rows is not None and check == "required-empty":
            counts = audit.required_counts_sql(audit.parse_candidates(rows))
            rows = [] if counts is None else _audit_query(counts, database, host, port, user)
        if rows is None:
            results.append(audit.Result(check, audit.UNREADABLE))
            continue
        match check:
            case "journal-codes":
                results.append(audit.journal_codes_result(rows))
            case "bank-duplicates":
                result, duplicates = audit.bank_duplicates_result(rows)
                results.append(result)
            case "bank-payments":
                results.append(audit.bank_payments_result(rows, duplicates))
            case "bank-closed-lines":
                results.append(audit.bank_closed_lines_result(rows, duplicates))
            case "constraints-missing":
                results.append(audit.constraints_result(rows))
            case "required-empty":
                results.append(audit.required_result(rows))
            case _:
                results.append(audit.stale_reconciled_result(rows))
    return results


def _print_audit_result(result: audit.Result) -> None:
    title, fix = _AUDIT_TEXT[result.check]
    title = t(title)
    match result.verdict:
        case audit.NOT_APPLICABLE:
            print(level_text("INFO", tf("{}: not applicable to this database.", title)))
            return
        case audit.UNREADABLE:
            print(level_text("ERROR", tf("{}: could not be read.", title)))
            return
        case audit.CLEAN:
            print(level_text("OK", tf("{}: none.", title)))
            return
    level = "WARN" if result.verdict == audit.FOUND else "INFO"
    print(level_text(level, f"{title}: {result.count}"))
    for example in result.examples:
        print(f"    {example}")
    if result.more:
        print("    " + tf("... and {} more", str(result.more)))
    if result.detail:
        print(f"    {result.detail}")
    print("    " + t(fix))


def migration_audit(database: str, host: str, port: int, user: str) -> int:
    """The coherence checks that apply to one database, and what each found."""
    if not DB_NAME_RE.fullmatch(database):
        print(level_text("ERROR", tf("Invalid database name: {}", database)))
        return UNKNOWN
    rows = _audit_query(audit.CATALOGUE_SQL, database, host, port, user)
    if rows is None:
        print(level_text("ERROR", tf("Cannot read the database {}.", database)))
        return UNKNOWN
    catalogue = audit.parse_catalogue(rows)
    if not audit.is_odoo(catalogue):
        print(level_text("ERROR", tf("{} is not an Odoo database.", database)))
        return UNKNOWN
    results = _run_audit(database, host, port, user, catalogue)
    for result in results:
        _print_audit_result(result)
    code = audit.exit_code(results)
    print(level_text("INFO", t(
        "Nothing was changed. Examples show ids and codes only; the fixes are named, not applied.")))
    return {1: FOUND, 2: UNKNOWN}.get(code, CLEAN)


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
