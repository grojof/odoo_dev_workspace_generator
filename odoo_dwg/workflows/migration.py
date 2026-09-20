"""Migration mode — OpenUpgrade chained upgrade 12 → 19.

Generates a migration environment (per-version clones, uv venvs with matched
interpreters, per-step configs, and a checkpointing `run_migration.sh`) for a
source → target chain, over plan → preview → apply. The chain is sequential (no
skips); every step runs natively in its own uv virtualenv. Running
the driver against a real source dump is a manual, host-side step.
"""

from __future__ import annotations

import re
import shlex
import time
from datetime import datetime
from pathlib import Path

from .. import analysis, egress, planners, preflight, runlog, templates
from ..i18n import t, tf
from ..models import (
    DB_NAME_RE,
    MODULE_NAME_RE,
    Command,
    MigrationEnv,
    ModuleDecision,
    PromotedModules,
    decisions_from_json,
    interpreter_from_pyvenv,
)
from ..planners import write_text_file_command
from ..prompts import ask_bool, ask_text, choose, clear_screen, confirm_with_phrase
from ..system import apply_commands, journal_since, list_dirs, preview_commands
from ..ui import level_text, render_table, title
from .common import redirect_mail


def _exists(path) -> bool:
    return path.exists()


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _stamp() -> str:
    """Suffix for this run's backups, so a later generation never overwrites one."""
    # Microseconds: two runs inside the same second shared a name, and the
    # second copy overwrote the first's backup.
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def _ask_env(with_oca: bool = False) -> MigrationEnv | None:
    source = ask_text("Source Odoo version (e.g. 13.0)", required=True)
    target = ask_text("Target Odoo version (e.g. 18.0)", required=True)
    # Only where they are acted on: generation clones and links them, and every
    # other action reads what generation already put on disk.
    raw_oca = (
        ask_text("OCA repositories this chain needs (comma-separated, optional)", "")
        if with_oca else ""
    )
    oca = [repo.strip() for repo in raw_oca.split(",") if repo.strip()]
    env = MigrationEnv(source=source, target=target, oca_repos=oca)
    try:
        env.validate()
    except ValueError as error:
        print(level_text("ERROR", str(error)))
        return None
    return env


def _interpreter_rows(env: MigrationEnv) -> list[tuple[str, str, str]]:
    """One row per chain step: the interpreter it will run and where it comes
    from, so the operator sees the whole chain before pinning anything."""
    rows: list[tuple[str, str, str]] = []
    for version in env.chain():
        choice = env.interpreter_choice(version)
        detail = t("pinned by you") if version in env.interpreter_overrides else t("recommended")
        # A pin is not persisted anywhere, so a later generation resolves the
        # recommendation again and would rebuild a venv that was deliberately
        # built on something else. Say what is on disk, before the preview.
        built = interpreter_from_pyvenv(
            version, _read_text(env.venv_dir(version) / "pyvenv.cfg") or ""
        )
        if built and built.python and built.python != choice.python:
            detail = tf("{} — the venv on disk was built with {}", detail, built.python)
        rows.append((version, choice.describe(), detail))
    return rows


def _choose_step_interpreters(env: MigrationEnv) -> bool:
    """Let the operator pin the interpreter of individual chain steps. Returns
    False when the operator cancels out of the whole flow."""
    while True:
        print(
            render_table(
                [t("Step"), t("Interpreter"), t("Source")],
                [list(row) for row in _interpreter_rows(env)],
            )
        )
        if not ask_bool("Pin a step to a specific Python version?", False):
            return True
        version = choose("Which step", list(env.chain()) + ["Back"], default_index=None)
        if version in ("", "Back"):
            return True
        support_default = env.interpreter_choice(version).python
        python = ask_text(tf("Python for Odoo {}", version), support_default, required=True)
        try:
            choice = env.set_interpreter_override(version, python)
        except ValueError as error:
            print(level_text("ERROR", str(error)))
            continue
        if choice.out_of_range:
            crossed = choice.crossed
            print(
                level_text(
                    "WARN",
                    tf(
                        "Python {} is outside the supported range for Odoo {} (bound: {}).",
                        python,
                        version,
                        crossed.describe() if crossed else "",
                    ),
                )
            )
            if not ask_bool("Pin it anyway?", False):
                env.clear_interpreter_override(version)


def _print_preflight(rows: list[tuple[str, str, str]]) -> None:
    print(render_table(["State", "Check", "Detail"], [list(row) for row in rows]))


def _generate_environment() -> None:
    env = _ask_env(with_oca=True)
    if env is None:
        return

    print(level_text("INFO", tf("Migration chain: {}", " -> ".join([env.source, *env.chain()]))))

    # Interpreters per step: the matrix recommends, the operator may pin.
    if not _choose_step_interpreters(env):
        print(level_text("INFO", t("Cancelled.")))
        return

    # Host-scope preflight first: fail early, informed — MISSING chain-required
    # tools do not hard-block (the plan itself may be what fixes the host), but
    # continuing is an explicit decision.
    rows = preflight.preflight_rows(preflight.gather_host_facts(env))
    _print_preflight(rows)
    if any(state == "MISSING" for state, _check, _detail in rows):
        if not ask_bool("Some required checks are MISSING — continue anyway?", False):
            print(level_text("INFO", t("Cancelled.")))
            return

    commands = planners.plan_generate_migration(
        env, exists=_exists, read=_read_text, stamp=_stamp()
    )
    preview_commands(commands)
    if ask_bool("Apply this plan now?", False):
        apply_commands(commands)
        print(level_text("OK", tf("Environment ready. Run: bash {}/run_migration.sh <source-dump>", env.root)))


def _read_decisions(path: Path) -> list[ModuleDecision]:
    """The operator's record of what was decided about modules with no successor.

    Absent or unreadable yields none: it is a hand-edited file carried between
    clients, and a typo in it must not stop a preflight from running.
    """
    text = _read_text(path)
    return decisions_from_json(text) if text else []


def _preflight_check() -> None:
    env = _ask_env()
    if env is None:
        return
    dump = ask_text("Source dump file to verify (empty to skip)", "", required=False)
    db = ask_text("Existing database to verify (empty to skip)", "", required=False)
    if db and not DB_NAME_RE.fullmatch(db):
        print(level_text("ERROR", tf("Invalid database name: {}", db)))
        return
    # Asked after the name is validated: a value the flow refuses should not cost
    # the operator another question first.
    raw_decisions = ask_text(
        "File recording what you decided about modules with no successor (empty to skip)",
        "", required=False,
    )
    decisions_path = Path(raw_decisions).expanduser() if raw_decisions.strip() else None

    host = preflight.gather_host_facts(env, dump or None)
    db_facts = preflight.gather_db_facts(env, db) if db else None
    coverage: preflight.Coverage | None = None
    customs: set[str] | None = None
    if db_facts is not None and db_facts.installed_modules:
        coverage = preflight.gather_coverage(
            env, db_facts.installed_modules, authors=db_facts.module_authors,
            decisions=_read_decisions(decisions_path) if decisions_path else [],
        )
        customs = coverage.customs

    rows = preflight.preflight_rows(
        host, db_facts, coverage, customs, custom_dir_for=env.addons_custom_dir
    )
    _print_preflight(rows)
    if any(state == "MISSING" for state, _check, _detail in rows):
        print(level_text("WARN", t("Resolve the MISSING checks before running the migration.")))
    else:
        print(level_text("OK", t("Preflight passed.")))


def _ask_promoted(required: bool) -> PromotedModules | None:
    """The operator's own place for reviewed code, one directory per version.

    Empty means "not using one": staging then derives every step, as it always
    did. A location inside the migration environments is refused, since cleaning
    one would take the only copy of the work with it.
    """
    raw = ask_text(
        "Directory holding your reviewed modules, one subdirectory per version "
        "(empty = none)",
        "",
        required=required,
    )
    if not raw.strip():
        return None
    promoted = PromotedModules(base_dir=raw.strip())
    try:
        promoted.validate()
    except ValueError as error:
        print(level_text("ERROR", str(error)))
        return None
    return promoted


def _promote_modules() -> None:
    """Copy reviewed module code out of an environment, so the next run can take
    it as given instead of deriving it again."""
    env = _ask_env()
    if env is None:
        return
    promoted = _ask_promoted(required=True)
    if promoted is None:
        return
    staged = sorted({
        path.name
        for version in env.chain()
        for path in _existing_dirs(env.addons_custom_dir(version))
    })
    if not staged:
        print(level_text("INFO", t("No staged modules in this environment.")))
        return
    module = choose("Which module", staged + ["Cancel"], default_index=None)
    if module in ("", "Cancel"):
        return
    versions = [v for v in env.chain() if (env.addons_custom_dir(v) / module).is_dir()]

    rows = preflight.divergence(env, module, promoted, versions)
    if rows:
        print(render_table(
            [t("Step"), t("Environment vs promoted")], [[v, t(state)] for v, state in rows]
        ))
    already = [v for v, state in rows if state in ("same", "diverged")]
    if already and not confirm_with_phrase(
        tf("This replaces the promoted code of {} for: {}.", module, ", ".join(already)),
        "PROMOTE",
    ):
        print(level_text("INFO", t("Cancelled.")))
        return

    commands = planners.plan_promote_module(env, module, versions, promoted)
    preview_commands(commands)
    if not ask_bool("Apply this plan now?", False):
        print(level_text("INFO", t("Cancelled.")))
        return
    apply_commands(commands)
    print(level_text("OK", tf("Promoted {} for: {}.", module, ", ".join(versions))))
    print(level_text("INFO", t(
        "The promoted copy is yours: commit it on the branch for that version if you keep it in git. "
        "The throwaway repository inside each stage directory is not that history."
    )))


def _existing_dirs(parent: Path):
    try:
        return [path for path in parent.iterdir() if path.is_dir()]
    except OSError:
        return []


def _open_items(env: MigrationEnv, latest, logs: dict) -> list[tuple[str, str]]:
    """What the run left unresolved. This is the section the report exists for:
    a step that did not finish, and a step that passed while its log holds an
    error — success and a clean log are not the same thing."""
    items: list[tuple[str, str]] = []
    for step in latest.steps:
        if step.outcome == "fail":
            items.append((
                tf("Step {} failed", step.version),
                tf("exit {} — see {}", step.code or "?", str(env.logs_dir / f"{step.version}.log")),
            ))
        elif step.outcome == "unfinished":
            items.append((
                tf("Step {} never finished", step.version),
                tf("started {} and recorded no outcome", step.started or "?"),
            ))
        errors = [entry for entry in logs.get(step.version, []) if entry.level in ("ERROR", "CRITICAL")]
        if errors and step.outcome == "ok":
            items.append((
                tf("Step {} passed with {} error line(s)", step.version, len(errors)),
                tf("first: {}", errors[0].first[:120]),
            ))
    remaining = [v for v in env.chain() if (latest.step(v) is None)]
    if remaining:
        items.append((
            tf("{} step(s) never ran in this run", len(remaining)),
            ", ".join(remaining),
        ))
    return items


def _migration_report() -> None:
    """Read back what the runs left: the driver's step log, each step's Odoo log,
    and what the outbound firewall answered inside each step's own window."""
    env = _ask_env()
    if env is None:
        return
    text = _read_text(env.steps_file)
    if not text:
        print(level_text("INFO", tf(
            "No run recorded yet in {} — the driver writes one line per event as it goes.",
            str(env.steps_file),
        )))
        return

    history = runlog.runs(runlog.parse_steps(text))
    latest = history[-1]
    logs = {
        step.version: runlog.summarise_log(
            _read_text(env.logs_dir / f"{step.version}.log") or ""
        )
        for step in latest.steps
    }
    # The firewall's answers, asked for by the step's own window rather than
    # estimated. `odoo-bin` only: what the *migration* reached for, not what the
    # host did while it ran.
    decisions = {}
    for step in latest.steps:
        since, until = step.window
        journal = journal_since(egress.OPENSNITCH_JOURNAL_TAG, since, until) if since else ""
        answers = runlog.summarise_decisions(journal, process="odoo-bin")
        if answers:
            decisions[step.version] = answers

    report = templates.render_migration_report(
        env, history, logs, decisions, _open_items(env, latest, logs)
    )
    target = env.reports_dir / f"report-{_stamp()}.md"
    commands = [
        Command(
            tf("Create {}", str(env.reports_dir)),
            f"mkdir -p {shlex.quote(str(env.reports_dir))}",
        ),
        *write_text_file_command(target, report),
    ]
    preview_commands(commands)
    if not ask_bool("Apply this plan now?", False):
        print(level_text("INFO", t("Cancelled.")))
        return
    apply_commands(commands)
    print(level_text("OK", tf("Report written: {}", str(target))))


#: How often the live view re-reads what the driver has written. The driver's
#: steps take minutes; a shorter tick would only spend the terminal.
WATCH_SECONDS = 2
#: Rows of log and of firewall answers the live view shows at once.
_WATCH_LINES = 8


def _watch_run() -> None:
    """Follow a chain while it runs, from what the driver writes as it goes.

    The driver is started by hand in another terminal, so this only reads: the
    step log for where the chain is, the current step's Odoo log for what it is
    saying, and the firewall's journal for what it has reached for since that
    step began.
    """
    env = _ask_env()
    if env is None:
        return
    if not env.steps_file.exists():
        print(level_text("INFO", tf(
            "Nothing to follow yet: {} appears when the driver starts.", str(env.steps_file)
        )))
        return

    print(level_text("INFO", t("Following the run. Ctrl-C stops watching; the driver keeps going.")))
    try:
        while True:
            history = runlog.runs(runlog.parse_steps(_read_text(env.steps_file) or ""))
            latest = history[-1] if history else None
            rows = runlog.live_view(latest, list(env.chain()), datetime.now().astimezone().isoformat())
            current = runlog.current_step(rows)

            clear_screen()
            print(title(tf("Migration {} → {}", env.source, env.target))
                  + (f"  ({latest.run})" if latest else ""))
            print(render_table(
                [t("Step"), t("State"), t("Elapsed")],
                [[row.version, t(row.state), row.elapsed or "—"] for row in rows],
            ))

            if current:
                entries = runlog.summarise_log(
                    _read_text(env.logs_dir / f"{current}.log") or ""
                )[:_WATCH_LINES]
                print(title(tf("{} — worth reading so far", current)))
                if entries:
                    print(render_table(
                        [t("Level"), t("Logger"), t("Count"), t("Message")],
                        [[e.level, e.logger, str(e.count), e.first[:90]] for e in entries],
                    ))
                else:
                    print(t("  nothing above INFO yet"))

                step = latest.step(current) if latest else None
                journal = journal_since(
                    egress.OPENSNITCH_JOURNAL_TAG, step.started if step else ""
                )
                reached = runlog.summarise_decisions(journal, process="odoo-bin")[:_WATCH_LINES]
                if reached:
                    print(title(t("Reached outside its own machine")))
                    for answer in reached:
                        print(f"  {answer.action} {answer.host} ×{answer.count} ({answer.rule})")

            if latest is not None and latest.outcome in ("ok", "fail"):
                print(level_text("OK" if latest.outcome == "ok" else "ERROR",
                                 tf("The run finished: {}.", latest.outcome)))
                # The live view follows the *running* step, so the last frame has
                # no log detail. The report is where the whole run is read.
                print(level_text("INFO", t(
                    "Use \"Report on the runs so far\" for what each step logged and what is left open."
                )))
                return
            time.sleep(WATCH_SECONDS)
    except KeyboardInterrupt:
        # Back to this menu rather than the top one: stopping a watch is not
        # abandoning the migration, and the driver is still running elsewhere.
        print(t("\nStopped watching. The driver is unaffected."))


def _clean_environment() -> None:
    base = Path(MigrationEnv.base_dir).expanduser()
    environments = [name for name in list_dirs(str(base)) if "-to-" in name]
    if not environments:
        print(level_text("INFO", tf("No migration environments found under {}.", str(base))))
        return
    name = choose("Which environment", environments + ["Cancel"], default_index=None)
    if name in ("", "Cancel"):
        return
    root = base / name
    include_repos = ask_bool(
        "Also remove the shared clones cache (.repos)? It serves every migration environment.",
        False,
    )
    commands = planners.plan_clean_migration(root, base / ".repos" if include_repos else None)
    preview_commands(commands)
    # The environment holds the operator's per-version staged code, which may
    # carry their own edits and exists nowhere else. `rm -rf <root>` takes it, so
    # the phrase is asked for with those modules named.
    staged = sorted({path.name for path in root.glob("addons/*/custom/*") if path.is_dir()})
    question = (
        tf("This permanently deletes {}, including the staged modules: {}.",
           str(root), ", ".join(staged))
        if staged
        else tf("This permanently deletes {}.", str(root))
    )
    if not confirm_with_phrase(question, "DELETE"):
        print(level_text("INFO", t("Cancelled.")))
        return
    apply_commands(commands)
    print(level_text("OK", t("Migration environment removed.")))
    # The environment is known here by its directory (e.g. `13-to-18`), which is
    # what its database is named after.
    print(level_text("INFO", tf(
        "The PostgreSQL migration database (if any) is untouched — drop it with "
        "`dropdb -h 127.0.0.1 -U odoo {}` when you want a fully clean run.",
        f"migration_{name.replace('-', '_')}",
    )))


def _step_analysis_records(env: MigrationEnv, version: str) -> list[analysis.AnalysisRecord]:
    """Aggregate every analysis file of the step's OpenUpgrade clone.

    Both the layout and the *name* differ by era: from 14.0 the files sit under
    ``openupgrade_scripts/scripts/<module>/<ver>/upgrade_analysis.txt``, while the
    ≤ 13 fork embeds them in each add-on's ``migrations/<ver>/`` and calls them
    ``openupgrade_analysis.txt``. Looking only for the newer name found nothing
    at all in the 12 → 13 step — the one hop where a module that has not moved
    since 12 has the most to answer for — and staging then reported no candidate
    findings, which reads exactly like having none. The work file the tool writes
    beside it (``…_work.txt``) is deliberately not read.
    """
    clone = env.openupgrade_clone_dir(version)
    records: list[analysis.AnalysisRecord] = []
    patterns = (
        "openupgrade_scripts/scripts/*/*/upgrade_analysis.txt",
        "addons/*/migrations/*/upgrade_analysis.txt",
        "odoo/addons/*/migrations/*/upgrade_analysis.txt",
        "addons/*/migrations/*/openupgrade_analysis.txt",
        "odoo/addons/*/migrations/*/openupgrade_analysis.txt",
    )
    for pattern in patterns:
        for path in clone.glob(pattern):
            try:
                records += analysis.parse_analysis(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return records


def _staged_module_files(module_dir: Path) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    for suffix in ("*.py", "*.xml"):
        for path in sorted(module_dir.rglob(suffix)):
            try:
                files.append((str(path.relative_to(module_dir)), path.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
    return files


def _ensure_staging_tool(env: MigrationEnv) -> bool:
    if (env.staging_tool_venv / "bin" / "odoo-module-migrate").exists():
        return True
    print(level_text("WARN", t("The staging tool (odoo-module-migrator) is not installed. This plan installs it:")))
    commands = planners.plan_staging_tool(env)
    preview_commands(commands)
    if not ask_bool("Apply this plan now?", False):
        return False
    apply_commands(commands)
    return True


def _stage_modules() -> None:
    env = _ask_env()
    if env is None:
        return
    if not _ensure_staging_tool(env):
        return

    promoted = _ask_promoted(required=False)
    source_dir = Path(ask_text("Directory containing your custom modules (at the source version)", required=True)).expanduser()
    if not source_dir.is_dir():
        print(level_text("ERROR", tf("Not a directory: {}", str(source_dir))))
        return
    available = list_dirs(str(source_dir))
    raw = ask_text("Modules to stage (comma-separated, empty = all)", "", required=False)
    modules = [m.strip() for m in raw.split(",") if m.strip()] or available
    malformed = [m for m in modules if not MODULE_NAME_RE.fullmatch(m)]
    if malformed:
        print(level_text("ERROR", tf("Not an Odoo module name: {}", ", ".join(malformed))))
        return
    unknown = [m for m in modules if m not in available]
    if unknown:
        print(level_text("ERROR", tf("Not found in the source directory: {}", ", ".join(unknown))))
        return
    if not modules:
        print(level_text("ERROR", t("No modules to stage.")))
        return

    missing_clones = [v for v in env.chain() if not env.openupgrade_clone_dir(v).is_dir()]
    if missing_clones:
        print(level_text("WARN", tf("No OpenUpgrade clone for {} — candidate detection will be empty for those steps (generate the environment first).", ", ".join(missing_clones))))

    already = sorted({m for m in modules for v in env.chain() if (env.addons_custom_dir(v) / m).exists()})
    if already and not confirm_with_phrase(
        tf("This replaces the already-staged code of: {}.", ", ".join(already)), "RESTAGE"
    ):
        print(level_text("INFO", t("Cancelled.")))
        return

    commands = []
    for module in modules:
        commands += planners.plan_stage_module(
            env, module, source_dir, promoted=promoted, exists=_exists
        )
    preview_commands(commands)
    if not ask_bool("Apply this plan now?", False):
        return
    apply_commands(commands)

    # Second phase: scan the staged output, then plan the additive scaffold and
    # report writes (previewed like everything else).
    write_commands = []
    # The records belong to the step, not to the module: read once per version
    # rather than once per (module, version), which re-globbed and re-parsed the
    # whole OpenUpgrade checkout for every module of every step.
    step_records = {version: _step_analysis_records(env, version) for version in env.chain()}
    for module in modules:
        steps: list[tuple[str, str, list, str | None]] = []
        for version in env.chain():
            log_path = env.staging_log_file(module, version)
            log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
            log_text = re.sub(r"\x1b\[[0-9;]*m", "", log_text)  # ANSI colors out of the report
            module_dir = env.addons_custom_dir(version) / module
            findings = analysis.scan_source(
                _staged_module_files(module_dir), step_records[version]
            )
            scaffold_path: str | None = None
            if findings:
                migrations_dir = module_dir / "migrations" / f"{version}.1.0.0"
                target = migrations_dir / "pre-migration.py"
                if target.exists():
                    # Never overwrite operator code — write an inert sibling.
                    target = migrations_dir / "pre-migration.generated.py"
                scaffold_path = str(target)
                write_commands.append(
                    Command(
                        tf("Create migrations directory for {} ({})", module, version),
                        f"mkdir -p {shlex.quote(str(migrations_dir))}",
                    )
                )
                write_commands += write_text_file_command(
                    target, templates.render_migration_scaffold(module, version, findings)
                )
            steps.append((version, log_text, findings, scaffold_path))
        drift = preflight.divergence(env, module, promoted, list(env.chain())) if promoted else []
        write_commands += write_text_file_command(
            env.staging_report_file(module),
            templates.render_staging_report(module, steps, promoted=drift),
        )
    preview_commands(write_commands)
    if ask_bool("Apply this plan now?", False):
        apply_commands(write_commands)
        for module in modules:
            print(level_text("OK", tf("Staging report: {}", env.staging_report_file(module))))
        print(level_text("INFO", t("Staging is a prepared starting point — your review completes the migration.")))


def migration_menu() -> None:
    while True:
        action = choose(
            "\nMigration (OpenUpgrade 12→19)",
            [
                "Generate a migration environment",
                "Preflight check",
                "Stage custom modules",
                "Promote reviewed modules",
                "Report on the runs so far",
                "Follow a running migration",
                "Clean a migration environment",
                "Redirect a database's mail to Mailpit",
                "Back",
            ],
            default_index=None,
        )
        if action in ("", "Back"):
            return
        if action == "Generate a migration environment":
            _generate_environment()
        elif action == "Preflight check":
            _preflight_check()
        elif action == "Stage custom modules":
            _stage_modules()
        elif action == "Promote reviewed modules":
            _promote_modules()
        elif action == "Report on the runs so far":
            _migration_report()
        elif action == "Follow a running migration":
            _watch_run()
        elif action == "Clean a migration environment":
            _clean_environment()
        elif action == "Redirect a database's mail to Mailpit":
            # Migration databases use the environment's defaults (host, port, role).
            defaults = MigrationEnv(source="12.0", target="19.0")
            redirect_mail(defaults.db_host, defaults.db_port, defaults.db_user)
