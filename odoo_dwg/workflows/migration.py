"""Migration mode — OpenUpgrade chained upgrade 12 → 19.

Generates a migration environment (per-version clones, uv venvs with matched
interpreters, per-step configs, and a checkpointing `run_migration.sh`) for a
source → target chain, over plan → preview → apply. The chain is sequential (no
skips); the step that runs Odoo 13 (Python 3.6) uses a Docker fallback. Running
the driver against a real source dump is a manual, host-side step.
"""

from __future__ import annotations

from .. import planners
from ..i18n import t, tf
from ..models import MigrationEnv
from ..prompts import ask_bool, ask_text, choose
from ..system import apply_commands, has_tool, preview_commands
from ..ui import level_text


def _exists(path) -> bool:
    return path.exists()


def _generate_environment() -> None:
    source = ask_text("Source Odoo version (e.g. 13.0)", required=True)
    target = ask_text("Target Odoo version (e.g. 18.0)", required=True)

    env = MigrationEnv(source=source, target=target)
    try:
        env.validate()
    except ValueError as error:
        print(level_text("ERROR", str(error)))
        return

    print(level_text("INFO", tf("Migration chain: {}", " -> ".join([source, *env.chain()]))))
    if not has_tool("uv"):
        print(level_text("WARN", t("uv is not installed — it is needed to build the native venvs (see provision).")))
    if env.needs_docker():
        print(level_text("WARN", t("This chain runs Odoo 13 (Python 3.6): Docker is required for that step.")))

    commands = planners.plan_generate_migration(env, exists=_exists)
    preview_commands(commands)
    if ask_bool("Apply this plan now?", False):
        apply_commands(commands)
        print(level_text("OK", tf("Environment ready. Run: bash {}/run_migration.sh <source-dump>", env.root)))


def migration_menu() -> None:
    while True:
        action = choose(
            "\nMigration (OpenUpgrade 12→19)",
            ["Generate a migration environment", "Back"],
            default_index=None,
        )
        if action in ("", "Back"):
            return
        if action == "Generate a migration environment":
            _generate_environment()
