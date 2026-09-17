"""Section 2 — Workspaces (create / manage). The core value of the tool.

Wires the pure planners (`odoo_dwg.planners`) to the terminal via the
plan → preview → confirm → apply contract. Create is create-only (it refuses to
clobber an existing workspace); manage acts on an existing workspace and gates a
destructive step behind an exact-phrase confirmation.
"""

from __future__ import annotations

from pathlib import Path

from .. import planners
from ..i18n import t, tf
from ..models import InterpreterChoice, WorkspaceConfig, odoo_major
from ..prompts import (
    ask_bool,
    ask_text,
    choose,
    choose_interpreter,
    confirm_with_phrase,
    select_file_path,
)
from ..system import (
    apply_commands,
    detect_python_version,
    list_dirs,
    preview_commands,
    uv_python_minors,
)
from ..ui import level_text


def _exists(path: Path) -> bool:
    return path.exists()


def _apply_if_confirmed(commands: list) -> None:
    if not commands:
        print(level_text("INFO", t("Nothing to do.")))
        return
    preview_commands(commands)
    if ask_bool("Apply this plan now?", False):
        apply_commands(commands)


def _resolve_interpreters(versions: list[str]) -> dict[str, InterpreterChoice] | None:
    """Resolve the interpreter for every version, asking only where the host's
    ``python3`` is outside the version's supported range. ``None`` means the
    operator cancelled."""
    host_python = detect_python_version()
    uv_minors = uv_python_minors()
    resolved: dict[str, InterpreterChoice] = {}
    for version in versions:
        choice = choose_interpreter(version, host_python, uv_minors)
        if choice is None:
            print(level_text("INFO", t("Cancelled.")))
            return None
        resolved[version] = choice
        print(
            level_text(
                "INFO", tf("Odoo {} venv will use Python {}.", version, choice.describe())
            )
        )
    return resolved


# --- create ---------------------------------------------------------------


def _quick_profile() -> WorkspaceConfig | None:
    name = ask_text("Workspace name", required=True)
    versions_raw = ask_text("Odoo versions (comma-separated)", "18.0", required=True)
    versions = [v.strip() for v in versions_raw.split(",") if v.strip()]
    oca_raw = ask_text("OCA repositories (comma-separated, optional)", "")
    oca = [r.strip() for r in oca_raw.split(",") if r.strip()]
    return WorkspaceConfig(name=name, versions=versions, oca_repos=oca)


def _load_profile() -> WorkspaceConfig | None:
    path = select_file_path(requested_label="workspace profile", allowed_extensions=(".json",))
    if not path:
        return None
    return WorkspaceConfig.load(path)


def _create_workspace() -> None:
    source = choose(
        "New workspace", ["New (quick)", "From a profile file", "Cancel"], default_index=None
    )
    if source in ("", "Cancel"):
        return
    cfg = _quick_profile() if source == "New (quick)" else _load_profile()
    if cfg is None:
        return

    cfg.normalize_defaults()
    try:
        cfg.validate()
    except ValueError as error:
        print(level_text("ERROR", str(error)))
        return

    # Create-only: never clobber an existing workspace.
    if cfg.root.exists():
        print(
            level_text(
                "WARN",
                tf("Workspace {} already exists — use manage to modify it.", str(cfg.root)),
            )
        )
        return

    interpreters = _resolve_interpreters(list(cfg.versions))
    if interpreters is None:
        return

    commands = planners.plan_generate_workspace(cfg, exists=_exists, interpreters=interpreters)
    preview_commands(commands)
    if ask_bool("Apply this plan now?", False):
        apply_commands(commands)
        print(level_text("OK", tf("Workspace {} created.", cfg.name)))


# --- manage ---------------------------------------------------------------


def _discover_workspaces() -> list[str]:
    # list_dirs already excludes dotted entries, so the .repos cache is skipped.
    return list_dirs(str(Path(WorkspaceConfig.base_dir).expanduser()))


def _load_existing(name: str) -> WorkspaceConfig | None:
    marker = WorkspaceConfig(name=name).profile_file
    if not marker.exists():
        print(level_text("WARN", tf("No workspace.json in {} — cannot manage it.", str(marker.parent))))
        return None
    return WorkspaceConfig.load(marker)


def _regenerate_venv(cfg: WorkspaceConfig) -> None:
    version = choose("Which version", list(cfg.versions) + ["Cancel"], default_index=None)
    if version in ("", "Cancel"):
        return
    if not confirm_with_phrase(
        tf("This removes and rebuilds .venv/odoo{}.", odoo_major(version)), "REBUILD"
    ):
        print(level_text("INFO", t("Cancelled.")))
        return
    interpreters = _resolve_interpreters([version])
    if interpreters is None:
        return
    _apply_if_confirmed(
        planners.plan_build_venv(
            cfg, version, recreate=True, interpreter=interpreters[version]
        )
    )


def _refresh_repos(cfg: WorkspaceConfig) -> None:
    commands = planners.plan_refresh_repos(cfg, exists=_exists)
    if not commands:
        print(level_text("INFO", t("No present clones to refresh.")))
        return
    _apply_if_confirmed(commands)


def _add_version(cfg: WorkspaceConfig) -> None:
    version = ask_text("New Odoo version (e.g. 19.0)", required=True)
    if version in cfg.versions:
        print(level_text("WARN", tf("{} is already in the workspace.", version)))
        return
    cfg.versions.append(version)
    cfg.normalize_defaults()
    try:
        cfg.validate()
    except ValueError as error:
        print(level_text("ERROR", str(error)))
        return
    # Clone if needed, regenerate the tree (new conf/scripts + updated profile),
    # and build the new version's venv if absent.
    commands = planners.plan_repo_cache(cfg, exists=_exists) + planners.plan_workspace_tree(cfg)
    if not cfg.venv_dir(version).exists():
        interpreters = _resolve_interpreters([version])
        if interpreters is None:
            return
        commands += planners.plan_build_venv(cfg, version, interpreter=interpreters[version])
    _apply_if_confirmed(commands)


def _manage_workspace() -> None:
    names = _discover_workspaces()
    if not names:
        print(level_text("INFO", t("No workspaces found.")))
        return
    name = choose("Existing workspaces", names + ["Back"], default_index=None)
    if name in ("", "Back"):
        return
    cfg = _load_existing(name)
    if cfg is None:
        return

    while True:
        action = choose(
            tf("Manage {}", cfg.name),
            ["Regenerate a venv", "Refresh shared repos", "Add a version", "Back"],
            default_index=None,
        )
        if action in ("", "Back"):
            return
        if action == "Regenerate a venv":
            _regenerate_venv(cfg)
        elif action == "Refresh shared repos":
            _refresh_repos(cfg)
        elif action == "Add a version":
            _add_version(cfg)


# --- entry ----------------------------------------------------------------


def workspace_menu() -> None:
    while True:
        action = choose(
            "\nWorkspaces",
            ["Create a workspace", "Manage an existing workspace", "Back"],
            default_index=None,
        )
        if action in ("", "Back"):
            return
        if action == "Create a workspace":
            _create_workspace()
        elif action == "Manage an existing workspace":
            _manage_workspace()
