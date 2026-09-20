"""Section 2 — Workspaces (create / manage). The core value of the tool.

Wires the pure planners (`odoo_dwg.planners`) to the terminal via the
plan → preview → confirm → apply contract. Create is create-only (it refuses to
clobber an existing workspace); manage acts on an existing workspace and gates a
destructive step behind an exact-phrase confirmation.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from .. import planners
from ..i18n import t, tf
from ..models import (
    InterpreterChoice,
    WorkspaceConfig,
    interpreter_from_pyvenv,
    odoo_major,
    resolve_interpreter,
    version_error,
)
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
from .common import apply_if_confirmed as _apply_if_confirmed
from .common import redirect_mail


def _exists(path: Path) -> bool:
    return path.exists()




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
    path = select_file_path(requested_label=t("workspace profile"), allowed_extensions=(".json",))
    if not path:
        return None
    return _load_valid(Path(path))


def _load_valid(path: Path) -> WorkspaceConfig | None:
    """Load, normalize and validate a profile; report why when it cannot be used.
    A profile may come from anyone, and its values reach paths, generated
    scripts and odoo.conf."""
    try:
        cfg = WorkspaceConfig.load(path)
        cfg.normalize_defaults()
        cfg.validate()
    except (OSError, ValueError, TypeError) as error:
        print(level_text("ERROR", tf("Cannot use the profile {}: {}", str(path), error)))
        return None
    return cfg


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
    cfg = _load_valid(marker)
    if cfg is not None and cfg.name != name:
        print(level_text("ERROR", tf("{} names another workspace ({}).", str(marker), cfg.name)))
        return None
    return cfg


def _stamp() -> str:
    """Suffix for this run's backups, so a later refresh never overwrites one."""
    # Microseconds: two runs inside the same second shared a name, and the
    # second copy overwrote the first's backup.
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def _read(path: Path) -> str | None:
    """Current text of a generated file, or None when there is none to compare.
    Undecodable bytes are replaced, so such a file counts as changed."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _existing_interpreters(cfg: WorkspaceConfig) -> dict[str, InterpreterChoice]:
    """The interpreter each present venv was built with (from its ``pyvenv.cfg``),
    so regenerated files describe and rebuild what is really there. A version
    without a venv gets the default the tool would pick for this host."""
    host_python = detect_python_version()
    resolved: dict[str, InterpreterChoice] = {}
    for version in cfg.versions:
        pyvenv = _read(cfg.venv_dir(version) / "pyvenv.cfg")
        choice = interpreter_from_pyvenv(version, pyvenv) if pyvenv else None
        resolved[version] = choice or resolve_interpreter(version, host_python=host_python)
    return resolved


def _refresh_files(cfg: WorkspaceConfig) -> None:
    commands = planners.plan_refresh_files(cfg, _existing_interpreters(cfg), _read, _stamp())
    if not commands:
        print(level_text("OK", t("Every generated file is already up to date.")))
        return
    print(
        level_text(
            "INFO",
            t("Only files that change are written; each existing one is kept as <file>.bak-<date> first."),
        )
    )
    _apply_if_confirmed(commands)




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
    error = version_error(version)
    if error:
        print(level_text("ERROR", error))
        return
    if version in cfg.versions:
        print(level_text("WARN", tf("{} is already in the workspace.", version)))
        return
    # Plan on a copy: the loaded profile changes only once the plan has run, so
    # a declined or failed plan leaves nothing half-added for later actions.
    candidate = replace(cfg, versions=[*cfg.versions, version])
    candidate.normalize_defaults()
    try:
        candidate.validate()
    except ValueError as error:
        print(level_text("ERROR", str(error)))
        return
    if _plan_added_version(candidate, version):
        cfg.versions = candidate.versions


def _plan_added_version(cfg: WorkspaceConfig, version: str) -> bool:
    # Clone if needed, link and refresh the generated files (new conf/scripts,
    # updated profile; hand-edited files kept as .bak), and build the new
    # version's venv unless a previous build finished (its ready marker) — every
    # other version keeps the interpreter its venv was really built with.
    interpreters = _existing_interpreters(cfg)
    if not cfg.venv_ready_marker(version).exists():
        chosen = _resolve_interpreters([version])
        if chosen is None:
            return False
        interpreters.update(chosen)
    commands = planners.plan_repo_cache(cfg, exists=_exists) + planners.plan_workspace_links(cfg)
    # The venv is built before the files are refreshed, so a failed build leaves
    # the workspace's profile listing only the versions it really has.
    if not cfg.venv_ready_marker(version).exists():
        commands += planners.plan_build_venv(cfg, version, interpreter=interpreters[version])
    commands += planners.plan_refresh_files(cfg, interpreters, _read, _stamp())
    return _apply_if_confirmed(commands)


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
            [
                "Refresh generated files",
                "Regenerate a venv",
                "Refresh shared repos",
                "Add a version",
                "Redirect a database's mail to Mailpit",
                "Back",
            ],
            default_index=None,
        )
        if action in ("", "Back"):
            return
        if action == "Refresh generated files":
            _refresh_files(cfg)
        elif action == "Regenerate a venv":
            _regenerate_venv(cfg)
        elif action == "Refresh shared repos":
            _refresh_repos(cfg)
        elif action == "Add a version":
            _add_version(cfg)
        elif action == "Redirect a database's mail to Mailpit":
            redirect_mail(cfg.db_host, cfg.db_port, cfg.db_user)


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
