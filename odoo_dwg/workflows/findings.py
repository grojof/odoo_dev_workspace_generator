"""The findings ledger from the menu: start it, add to it, decide, and write the reports.

Every change to the ledger rewrites the whole file through a previewed plan, so
what the operator confirms is the file that will be on disk. Reading it — list,
show, validate, render, check links — is in ``checks`` and writes nothing.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable
from datetime import date
from pathlib import Path

from .. import findings as fl
from ..i18n import t, tf
from ..models import MigrationEnv
from ..planners import write_text_file_command
from ..prompts import ask_text, choose
from ..system import Command, read_text, url_status
from ..ui import level_text, render_table
from .common import apply_if_confirmed

REPORT_KINDS = ("client", "extended")


def load_ledger(env: MigrationEnv) -> fl.Ledger | None:
    """The environment's ledger, or None after saying why there is none to use."""
    text = read_text(str(env.findings_ledger))
    if text is None:
        print(level_text("INFO", tf(
            "No findings ledger yet in {}. Menu -> Migration -> Findings -> Start a findings "
            "ledger starts one.", str(env.findings_ledger))))
        return None
    try:
        return fl.parse_ledger(text)
    except fl.LedgerError as error:
        print(level_text("ERROR", tf("The findings ledger {} cannot be used:",
                                     str(env.findings_ledger))))
        for problem in error.problems:
            print(f"  - {problem}")
        return None


def load_tables(env: MigrationEnv, ledger: fl.Ledger) -> dict[str, list[list[str]]]:
    """Every table a finding attaches, parsed; an unreadable one is left out, and
    the renderer names it."""
    tables: dict[str, list[list[str]]] = {}
    for finding in ledger.findings:
        for ref in finding.tables:
            text = read_text(str(env.findings_data_dir / ref.file))
            if text is not None:
                tables[ref.file] = fl.parse_tsv(text)
    return tables


def render(env: MigrationEnv, ledger: fl.Ledger, kind: str, lang: str, today: date) -> str:
    renderer = fl.render_client_report if kind == "client" else fl.render_extended_report
    return renderer(ledger, load_tables(env, ledger), lang, today)


def report_path(env: MigrationEnv, kind: str, lang: str) -> Path:
    return env.reports_dir / f"findings-{kind}.{lang}.md"


def broken_links(
    ledger: fl.Ledger, status: Callable[[str], tuple[int | None, str]] | None = None
) -> list[tuple[str, str, str]]:
    """``(where, url, what it answered)`` for every link that does not answer 2xx."""
    ask = status or url_status
    broken = []
    for where, url in fl.ledger_urls(ledger):
        code, error = ask(url)
        if code is None or not 200 <= code < 300:
            broken.append((where, url, str(code) if code is not None else error))
    return broken


def print_findings(ledger: fl.Ledger) -> None:
    rows = [[f.id, f.severity, f.audience, f.decision.state] for f in ledger.findings]
    print(render_table(["Id", "Severity", "Audience", "Decision"], rows))


# --- writing -----------------------------------------------------------------------

def _write_ledger(env: MigrationEnv, ledger: fl.Ledger) -> bool:
    commands = [
        Command(tf("Create {}", str(env.findings_data_dir)),
                f"mkdir -p {shlex.quote(str(env.findings_data_dir))}"),
        *write_text_file_command(env.findings_ledger, fl.dump_ledger(ledger)),
    ]
    if apply_if_confirmed(commands):
        print(level_text("OK", tf("Findings ledger written: {}", str(env.findings_ledger))))
        return True
    print(level_text("INFO", t("Cancelled.")))
    return False


def _start(env: MigrationEnv) -> None:
    if env.findings_ledger.exists():
        print(level_text("INFO", tf("{} already exists; it is not replaced.",
                                    str(env.findings_ledger))))
        return
    client = ask_text("Client name", required=True)
    database = ask_text("Client database name", required=True)
    reference = ask_text("Reference database (the restored copy never modified)",
                         f"{database}_original")
    try:
        ledger = fl.new_ledger(client, database, env.source, env.target, reference)
    except fl.LedgerError as error:
        print(level_text("ERROR", str(error)))
        return
    _write_ledger(env, ledger)


def _apply(env: MigrationEnv, change: Callable[[fl.Ledger], fl.Ledger]) -> None:
    ledger = load_ledger(env)
    if ledger is None:
        return
    try:
        updated = change(ledger)
    except fl.LedgerError as error:
        print(level_text("ERROR", t("Nothing was changed:")))
        for problem in error.problems:
            print(f"  - {problem}")
        return
    _write_ledger(env, updated)


def _choose_finding(ledger: fl.Ledger) -> str:
    if not ledger.findings:
        print(level_text("INFO", t("The ledger holds no findings.")))
        return ""
    print_findings(ledger)
    return choose("Which finding", [f.id for f in ledger.findings] + ["Cancel"])


def _add(env: MigrationEnv) -> None:
    path = ask_text("JSON file with the findings to add", required=True)
    text = read_text(str(Path(path).expanduser()))
    if text is None:
        print(level_text("ERROR", tf("Cannot read {}.", path)))
        return
    _apply(env, lambda ledger: fl.add_findings(ledger, fl.parse_findings(text)))


def _decide(env: MigrationEnv) -> None:
    ledger = load_ledger(env)
    if ledger is None:
        return
    finding = _choose_finding(ledger)
    if finding in ("", "Cancel"):
        return
    state = choose("Decision", list(fl.DECISIONS) + ["Cancel"])
    if state in ("", "Cancel"):
        return
    note = ask_text("Who decided, and why", "")
    today = date.today().isoformat()
    _apply(env, lambda led: fl.decide(led, finding, state, today, note))


def _phase(env: MigrationEnv) -> None:
    ledger = load_ledger(env)
    if ledger is None:
        return
    print(render_table(["Id", "State"], [[p.id, p.state] for p in ledger.phases]))
    phase = choose("Which phase", [p.id for p in ledger.phases] + ["Cancel"])
    if phase in ("", "Cancel"):
        return
    state = choose("New state", list(fl.PHASE_STATES) + ["Cancel"])
    if state in ("", "Cancel"):
        return
    _apply(env, lambda led: fl.set_phase(led, phase, state))


def _withdraw(env: MigrationEnv) -> None:
    ledger = load_ledger(env)
    if ledger is None:
        return
    finding = _choose_finding(ledger)
    if finding in ("", "Cancel"):
        return
    reason = ask_text("Why it was wrong (kept in the corrections log)", required=True)
    today = date.today().isoformat()
    _apply(env, lambda led: fl.withdraw(led, finding, today, reason))


def _write_reports(env: MigrationEnv) -> None:
    ledger = load_ledger(env)
    if ledger is None:
        return
    lang = choose("Report language", list(fl.LANGUAGES) + ["Cancel"])
    if lang in ("", "Cancel"):
        return
    today = date.today()
    commands = [Command(tf("Create {}", str(env.reports_dir)),
                        f"mkdir -p {shlex.quote(str(env.reports_dir))}")]
    try:
        for kind in REPORT_KINDS:
            commands += write_text_file_command(report_path(env, kind, lang),
                                                render(env, ledger, kind, lang, today))
    except fl.LedgerError as error:
        print(level_text("ERROR", t("No report was written:")))
        for problem in error.problems:
            print(f"  - {problem}")
        return
    if apply_if_confirmed(commands):
        for kind in REPORT_KINDS:
            print(level_text("OK", tf("Report written: {}", str(report_path(env, kind, lang)))))


def _list(env: MigrationEnv) -> None:
    ledger = load_ledger(env)
    if ledger is not None:
        print_findings(ledger)


def findings_menu(env: MigrationEnv) -> None:
    actions = {
        "List the findings": lambda: _list(env),
        "Start a findings ledger": lambda: _start(env),
        "Add findings from a JSON file": lambda: _add(env),
        "Record a decision": lambda: _decide(env),
        "Set a phase's state": lambda: _phase(env),
        "Withdraw a finding": lambda: _withdraw(env),
        "Write the reports": lambda: _write_reports(env),
    }
    while True:
        action = choose(tf("\nFindings ({} → {})", env.source, env.target),
                        list(actions) + ["Back"])
        if action in ("", "Back"):
            return
        actions[action]()
