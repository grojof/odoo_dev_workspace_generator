"""Pure command builders — the *plan* half of plan → preview → apply.

Every function returns a ``list[Command]`` and performs no I/O and no execution;
``system.apply_commands`` is the only thing that runs them. Existence checks are
injected (``exists`` predicate) so planners stay pure and testable while still
being able to *omit* work that is already present (e.g. a clone already in the
shared cache). The default predicate assumes nothing exists.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable
from pathlib import Path

from . import templates
from .i18n import tf
from .models import WorkspaceConfig, odoo_major
from .system import Command

Exists = Callable[[Path], bool]


def _never(_path: Path) -> bool:
    return False


def write_text_file_command(path: Path | str, content: str, mode: str = "644") -> list[Command]:
    """Emit a file via a quoted heredoc plus a ``chmod`` — mirrors the sibling app."""
    target = str(path)
    return [
        Command(tf("Write {}", target), f"cat > {shlex.quote(target)} <<'EOF'\n{content}\nEOF"),
        Command(tf("Set mode {} on {}", mode, target), f"chmod {mode} {shlex.quote(target)}"),
    ]


def plan_repo_cache(cfg: WorkspaceConfig, exists: Exists = _never) -> list[Command]:
    """Clone each Odoo version and each OCA repo into the shared cache, once.

    A clone already present (``exists`` true) is skipped, never re-cloned or
    mutated. Uses ``--branch <version> --single-branch`` per the official source
    install.
    """
    commands: list[Command] = []
    for version in cfg.versions:
        dest = cfg.odoo_clone_dir(version)
        if exists(dest):
            continue
        commands.append(
            Command(
                tf("Clone Odoo {} into the shared cache", version),
                f"git clone --branch {shlex.quote(version)} --single-branch "
                f"{shlex.quote(cfg.odoo_repo_url)} {shlex.quote(str(dest))}",
            )
        )
    for repo in cfg.oca_repos:
        for version in cfg.versions:
            dest = cfg.oca_clone_dir(repo, version)
            if exists(dest):
                continue
            url = f"{cfg.oca_url_base}/{repo}.git"
            commands.append(
                Command(
                    tf("Clone OCA {} ({}) into the shared cache", repo, version),
                    f"git clone --branch {shlex.quote(version)} --single-branch "
                    f"{shlex.quote(url)} {shlex.quote(str(dest))}",
                )
            )
    return commands


def plan_workspace_tree(cfg: WorkspaceConfig) -> list[Command]:
    """Create the per-client workspace tree and write every generated file.

    Pure and create-friendly: directory creation is idempotent (``mkdir -p``) and
    the OCA symlinks use ``ln -sfn``; the create-only guard (refusing to clobber an
    existing workspace) lives in the workflow, not here.
    """
    commands: list[Command] = [
        Command(
            tf("Create workspace directories for {}", cfg.name),
            "mkdir -p "
            + " ".join(
                shlex.quote(str(p))
                for p in (
                    cfg.addons_custom_dir,
                    cfg.addons_oca_dir,
                    cfg.config_dir,
                    cfg.scripts_dir,
                    cfg.vscode_dir,
                )
            ),
        )
    ]

    # OCA symlinks, per version, into the shared cache.
    for repo in cfg.oca_repos:
        for version in cfg.versions:
            link = cfg.oca_symlink_dir(repo, version)
            target = cfg.oca_clone_dir(repo, version)
            commands.append(
                Command(
                    tf("Link OCA {} for Odoo {}", repo, version),
                    f"mkdir -p {shlex.quote(str(link.parent))} && "
                    f"ln -sfn {shlex.quote(str(target))} {shlex.quote(str(link))}",
                )
            )

    # Per-version odoo.conf and run scripts.
    for version in cfg.versions:
        major = odoo_major(version)
        commands += write_text_file_command(
            cfg.config_file(version), templates.render_odoo_conf(cfg, version), "644"
        )
        commands += write_text_file_command(
            cfg.scripts_dir / f"run-odoo{major}.sh",
            templates.render_run_sh(cfg, version),
            "755",
        )

    # Workspace-wide scripts and editor files.
    commands += write_text_file_command(
        cfg.scripts_dir / "setup_venv.sh", templates.render_setup_venv_sh(cfg), "755"
    )
    commands += write_text_file_command(
        cfg.vscode_dir / "settings.json", templates.render_vscode_settings(cfg)
    )
    commands += write_text_file_command(
        cfg.vscode_dir / "extensions.json", templates.render_vscode_extensions()
    )
    commands += write_text_file_command(
        cfg.vscode_dir / "tasks.json", templates.render_vscode_tasks(cfg)
    )
    commands += write_text_file_command(
        cfg.vscode_dir / "launch.json", templates.render_vscode_launch(cfg)
    )
    commands += write_text_file_command(
        cfg.code_workspace_file, templates.render_code_workspace(cfg)
    )
    commands += write_text_file_command(cfg.readme_file, templates.render_workspace_readme(cfg))
    return commands


def plan_build_venv(cfg: WorkspaceConfig, version: str, recreate: bool = False) -> list[Command]:
    """Build one instance venv and install its version-matched requirements.

    ``recreate`` removes an existing venv first (management "regenerate"); by
    default it does not, so generation can skip versions whose venv already exists
    by simply not calling this.
    """
    venv = cfg.venv_dir(version)
    odoo = cfg.odoo_clone_dir(version)
    commands: list[Command] = []
    if recreate:
        commands.append(
            Command(tf("Remove existing venv {}", str(venv)), f"rm -rf {shlex.quote(str(venv))}")
        )
    commands += [
        Command(
            tf("Create venv {}", str(venv)),
            f"python3 -m venv {shlex.quote(str(venv))}",
        ),
        Command(
            tf("Upgrade pip/wheel/setuptools in {}", str(venv)),
            f"{shlex.quote(str(venv / 'bin' / 'pip'))} install --upgrade pip wheel setuptools",
        ),
        Command(
            tf("Install Odoo {} requirements", version),
            f"{shlex.quote(str(venv / 'bin' / 'pip'))} install -r "
            f"{shlex.quote(str(odoo / 'requirements.txt'))}",
        ),
    ]
    return commands
