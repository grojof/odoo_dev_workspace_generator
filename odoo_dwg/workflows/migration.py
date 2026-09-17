"""Migration mode — OpenUpgrade chained upgrade 12 → 19.

Generates a migration environment (per-version clones, uv venvs with matched
interpreters, per-step configs, and a checkpointing `run_migration.sh`) for a
source → target chain, over plan → preview → apply. The chain is sequential (no
skips); the step that runs Odoo 13 (Python 3.6) uses a Docker fallback. Running
the driver against a real source dump is a manual, host-side step.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from .. import analysis, planners, preflight, templates
from ..i18n import t, tf
from ..models import DOCKER_PYTHON, MigrationEnv
from ..planners import write_text_file_command
from ..prompts import ask_bool, ask_text, choose, confirm_with_phrase
from ..system import Command, apply_commands, list_dirs, preview_commands
from ..ui import level_text, render_table


def _exists(path) -> bool:
    return path.exists()


def _ask_env() -> MigrationEnv | None:
    source = ask_text("Source Odoo version (e.g. 13.0)", required=True)
    target = ask_text("Target Odoo version (e.g. 18.0)", required=True)
    env = MigrationEnv(source=source, target=target)
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
        pinned = version in env.interpreter_overrides
        if choice.source == DOCKER_PYTHON:
            detail = t("fixed by the official image")
        elif pinned:
            detail = t("pinned by you")
        else:
            detail = t("recommended")
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
        native = [v for v in env.chain() if env.interpreter_choice(v).source != DOCKER_PYTHON]
        if not native:
            print(level_text("INFO", t("Every step in this chain runs from a Docker image.")))
            return True
        version = choose(t("Which step"), native + [t("Back")], default_index=None)
        if version in ("", t("Back")):
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
    env = _ask_env()
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

    commands = planners.plan_generate_migration(env, exists=_exists)
    preview_commands(commands)
    if ask_bool("Apply this plan now?", False):
        apply_commands(commands)
        print(level_text("OK", tf("Environment ready. Run: bash {}/run_migration.sh <source-dump>", env.root)))


def _preflight_check() -> None:
    env = _ask_env()
    if env is None:
        return
    dump = ask_text("Source dump file to verify (empty to skip)", "", required=False)
    db = ask_text("Existing database to verify (empty to skip)", "", required=False)

    host = preflight.gather_host_facts(env, dump or None)
    db_facts = preflight.gather_db_facts(env, db) if db else None
    coverage: preflight.Coverage | None = None
    customs: set[str] | None = None
    if db_facts is not None and db_facts.installed_modules:
        coverage = preflight.gather_coverage(
            env, db_facts.installed_modules, authors=db_facts.module_authors
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
    if not confirm_with_phrase(tf("This permanently deletes {}.", str(root)), "DELETE"):
        print(level_text("INFO", t("Cancelled.")))
        return
    apply_commands(commands)
    print(level_text("OK", t("Migration environment removed.")))
    print(level_text("INFO", t("The PostgreSQL migration database (if any) is untouched — drop it with dropdb when you want a fully clean run.")))


def _step_analysis_records(env: MigrationEnv, version: str) -> list[analysis.AnalysisRecord]:
    """Aggregate every ``upgrade_analysis.txt`` of the step's OpenUpgrade clone.
    Layout differs by era: ``openupgrade_scripts/scripts/<module>/<ver>/`` on
    ≥ 14, module-embedded ``migrations`` dirs on the ≤ 13 fork."""
    clone = env.openupgrade_clone_dir(version)
    records: list[analysis.AnalysisRecord] = []
    patterns = (
        "openupgrade_scripts/scripts/*/*/upgrade_analysis.txt",
        "addons/*/migrations/*/upgrade_analysis.txt",
        "odoo/addons/*/migrations/*/upgrade_analysis.txt",
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

    source_dir = Path(ask_text("Directory containing your custom modules (at the source version)", required=True)).expanduser()
    if not source_dir.is_dir():
        print(level_text("ERROR", tf("Not a directory: {}", str(source_dir))))
        return
    available = list_dirs(str(source_dir))
    raw = ask_text("Modules to stage (comma-separated, empty = all)", "", required=False)
    modules = [m.strip() for m in raw.split(",") if m.strip()] or available
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
        commands += planners.plan_stage_module(env, module, source_dir)
    preview_commands(commands)
    if not ask_bool("Apply this plan now?", False):
        return
    apply_commands(commands)

    # Second phase: scan the staged output, then plan the additive scaffold and
    # report writes (previewed like everything else).
    write_commands = []
    for module in modules:
        steps: list[tuple[str, str, list, str | None]] = []
        for version in env.chain():
            log_path = env.staging_log_file(module, version)
            log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
            log_text = re.sub(r"\x1b\[[0-9;]*m", "", log_text)  # ANSI colors out of the report
            module_dir = env.addons_custom_dir(version) / module
            findings = analysis.scan_source(
                _staged_module_files(module_dir), _step_analysis_records(env, version)
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
        write_commands += write_text_file_command(
            env.staging_report_file(module), templates.render_staging_report(module, steps)
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
                "Clean a migration environment",
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
        elif action == "Clean a migration environment":
            _clean_environment()
