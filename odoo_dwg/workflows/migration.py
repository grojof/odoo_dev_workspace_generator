"""Migration mode — OpenUpgrade chained upgrade 12 → 19.

Generates a migration environment (per-version clones, uv venvs with matched
interpreters, per-step configs, and a checkpointing `run_migration.sh`) for a
source → target chain, over plan → preview → apply. The chain is sequential (no
skips); the step that runs Odoo 13 (Python 3.6) uses a Docker fallback. Running
the driver against a real source dump is a manual, host-side step.
"""

from __future__ import annotations

from pathlib import Path

from .. import planners, preflight
from ..i18n import t, tf
from ..models import MigrationEnv
from ..prompts import ask_bool, ask_text, choose, confirm_with_phrase
from ..system import apply_commands, list_dirs, preview_commands
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


def _print_preflight(rows: list[tuple[str, str, str]]) -> None:
    print(render_table(["State", "Check", "Detail"], [list(row) for row in rows]))


def _generate_environment() -> None:
    env = _ask_env()
    if env is None:
        return

    print(level_text("INFO", tf("Migration chain: {}", " -> ".join([env.source, *env.chain()]))))

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
    coverage: dict[str, list[str]] | None = None
    customs: set[str] | None = None
    if db_facts is not None and db_facts.installed_modules:
        coverage, customs = preflight.gather_coverage(env, db_facts.installed_modules)

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


def migration_menu() -> None:
    while True:
        action = choose(
            "\nMigration (OpenUpgrade 12→19)",
            [
                "Generate a migration environment",
                "Preflight check",
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
        elif action == "Clean a migration environment":
            _clean_environment()
