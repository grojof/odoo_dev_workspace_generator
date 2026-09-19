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
from .models import (
    PKG_RESOURCES_LAST_MAJOR,
    SETUPTOOLS_PIN,
    UV_PYTHON,
    InterpreterChoice,
    MigrationEnv,
    WorkspaceConfig,
    odoo_major,
    setuptools_requirement,
)
from .system import Command

Exists = Callable[[Path], bool]


def _never(_path: Path) -> bool:
    return False


def heredoc_delimiter(content: str, base: str = "EOF") -> str:
    """A heredoc delimiter that no line of ``content`` equals.

    A quoted heredoc copies its body literally — no expansion — so the only way
    for content to reach the shell is a line equal to the delimiter, which ends
    the heredoc early and runs whatever follows. Profile values (a host, a prefix,
    an OCA repo name) end up in generated files, so the delimiter must be chosen
    against the content rather than assumed absent."""
    lines = set(content.splitlines())
    delimiter = base
    while delimiter in lines:
        delimiter += "_"
    return delimiter


def write_text_file_command(path: Path | str, content: str, mode: str = "644") -> list[Command]:
    """Emit a file via a quoted heredoc plus a ``chmod`` — mirrors the sibling app."""
    target = str(path)
    end = heredoc_delimiter(content)
    return [
        Command(tf("Write {}", target), f"cat > {shlex.quote(target)} <<'{end}'\n{content}\n{end}"),
        Command(tf("Set mode {} on {}", mode, target), f"chmod {mode} {shlex.quote(target)}"),
    ]


def plan_repo_cache(cfg: WorkspaceConfig, exists: Exists = _never) -> list[Command]:
    """Clone each Odoo version and each OCA repo into the shared cache, once.

    A clone already present (``exists`` true) is skipped, never re-cloned or
    mutated, whether it is shallow or full. Clones are shallow
    (``--depth 1 --branch <version> --single-branch``): a development workspace
    never reads the branch history, which is most of a clone's size (an Odoo
    branch is ~5 GB with history, ~1 GB without). ``git fetch --unshallow``
    restores it for whoever needs ``log``/``blame``, and refreshing with
    ``pull --ff-only`` works the same on a shallow clone.
    """
    commands: list[Command] = []
    for version in cfg.versions:
        dest = cfg.odoo_clone_dir(version)
        if exists(dest):
            continue
        commands.append(
            Command(
                tf("Clone Odoo {} into the shared cache", version),
                f"git clone --depth 1 --branch {shlex.quote(version)} --single-branch "
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
                    f"git clone --depth 1 --branch {shlex.quote(version)} --single-branch "
                    f"{shlex.quote(url)} {shlex.quote(str(dest))}",
                )
            )
    return commands


def plan_workspace_tree(
    cfg: WorkspaceConfig,
    interpreters: dict[str, InterpreterChoice] | None = None,
) -> list[Command]:
    """Create the per-client workspace tree and write every generated file.

    Pure and create-friendly: directory creation is idempotent (``mkdir -p``) and
    the OCA symlinks use ``ln -sfn``; the create-only guard (refusing to clobber an
    existing workspace) lives in the workflow, not here.

    ``interpreters`` is passed through to the generated ``setup_venv.sh`` so the
    script rebuilds each venv with the interpreter the plan chose.
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
        cfg.scripts_dir / "setup_venv.sh",
        templates.render_setup_venv_sh(cfg, interpreters),
        "755",
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
    # Only when the language server can open at least one version (it refuses < 14).
    if templates.odools_versions(cfg):
        commands += write_text_file_command(cfg.odools_file, templates.render_odools_toml(cfg))
    commands += write_text_file_command(cfg.readme_file, templates.render_workspace_readme(cfg))
    # Save the profile marker so the workspace can be re-loaded for management.
    commands += write_text_file_command(cfg.profile_file, cfg.to_json())
    return commands


# --- provisioning (F2) -----------------------------------------------------

# Odoo build/system dependencies (Debian/Ubuntu apt). This is the set validated
# end-to-end during F1 acceptance on Ubuntu 24.04.
BUILD_DEPS: tuple[str, ...] = (
    "build-essential", "pkg-config", "python3-dev", "python3-venv", "python3-pip", "git",
    "libpq-dev", "libldap2-dev", "libsasl2-dev", "libssl-dev", "libffi-dev",
    "libxml2-dev", "libxslt1-dev", "libjpeg-dev", "zlib1g-dev", "libtiff-dev",
    "libopenjp2-7-dev", "liblcms2-dev", "libwebp-dev", "libharfbuzz-dev",
    "libfribidi-dev", "fontconfig", "postgresql-client",
)

# Pinned patched wkhtmltopdf 0.12.6.1-3 assets (amd64) with SHA-256, ported from
# the sibling app (verified against Odoo's own Dockerfile checksum). Codenames
# without a compatible asset resolve to None so the caller recommends the distro
# package or skip — never a guessed URL.
_WKHTMLTOPDF_BASE_URL = "https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3"
_WKHTMLTOPDF_ASSETS: dict[str, tuple[str, str]] = {
    # Upstream ships no noble build; the jammy one is what installs on 24.04.
    "noble": ("wkhtmltox_0.12.6.1-3.jammy_amd64.deb",
              "4f723b2691ad8638a9df960e0421d346d7315083e3583a334f33362280ddba15"),
}


def wkhtmltopdf_target_version(major: int) -> str:
    """Odoo-recommended wkhtmltopdf: 0.12.5 for Odoo <= 14, 0.12.6 for >= 15."""
    return "0.12.5" if major <= 14 else "0.12.6"


def resolve_wkhtmltopdf_asset(codename: str) -> tuple[str, str, str] | None:
    """``(url, filename, sha256)`` for the patched 0.12.6 build matching ``codename``,
    or None when no verified asset is pinned (caller recommends distro/skip)."""
    entry = _WKHTMLTOPDF_ASSETS.get((codename or "").strip().lower())
    if not entry:
        return None
    filename, sha256 = entry
    return f"{_WKHTMLTOPDF_BASE_URL}/{filename}", filename, sha256


def plan_build_deps() -> list[Command]:
    """Idempotent apt install of the Odoo build/system dependencies."""
    packages = " ".join(BUILD_DEPS)
    return [
        Command(tf("Update apt package lists"), "apt-get update"),
        Command(tf("Install Odoo build dependencies"), f"apt-get -y install {packages}"),
    ]


def plan_postgresql(role: str) -> list[Command]:
    """Install PostgreSQL, enable/start it, create an idempotent LOGIN CREATEDB dev
    role, and set loopback (127.0.0.1/::1) to trust for local development."""
    role_sql = (
        "DO $$ BEGIN "
        f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{role}') THEN "
        f"CREATE ROLE {role} WITH LOGIN CREATEDB; "
        "END IF; END $$;"
    )
    return [
        Command(tf("Install PostgreSQL"), "apt-get update && apt-get -y install postgresql"),
        Command(tf("Enable and start PostgreSQL"), "systemctl enable --now postgresql"),
        Command(
            tf("Create development role {} (if missing)", role),
            f"sudo -u postgres psql -v ON_ERROR_STOP=1 -c {shlex.quote(role_sql)}",
        ),
        Command(
            tf("Trust loopback connections for local development (pg_hba)"),
            'PGHBA=$(sudo -u postgres psql -tAc "SHOW hba_file;") && '
            'sed -ri "s#^(host\\s+all\\s+all\\s+127\\.0\\.0\\.1/32\\s+)\\S+#\\1trust#" "$PGHBA" && '
            'sed -ri "s#^(host\\s+all\\s+all\\s+::1/128\\s+)\\S+#\\1trust#" "$PGHBA"',
        ),
        Command(tf("Reload PostgreSQL"), "systemctl reload postgresql"),
    ]


def plan_wkhtmltopdf(major: int, codename: str) -> list[Command]:
    """Install the Odoo-recommended patched wkhtmltopdf for the host codename,
    verifying its SHA-256 (abort on mismatch). Returns no commands when no verified
    asset is pinned (0.12.5/<=14 or an unmapped codename) — caller recommends distro."""
    if wkhtmltopdf_target_version(major) != "0.12.6":
        return []
    asset = resolve_wkhtmltopdf_asset(codename)
    if asset is None:
        return []
    url, filename, sha256 = asset
    tmp = f"/tmp/{filename}"
    return [
        Command(tf("Ensure curl is available"),
                "command -v curl >/dev/null 2>&1 || (apt-get update && apt-get -y install curl)"),
        Command(tf("Download patched wkhtmltopdf ({})", filename),
                f"curl -fSL -o {shlex.quote(tmp)} {shlex.quote(url)}"),
        Command(tf("Verify wkhtmltopdf SHA-256 (abort on mismatch)"),
                f"echo {shlex.quote(sha256 + '  ' + tmp)} | sha256sum -c -"),
        Command(tf("Install verified wkhtmltopdf .deb"),
                f"apt-get -y install {shlex.quote(tmp)}"),
        Command(tf("Remove downloaded wkhtmltopdf .deb"), f"rm -f {shlex.quote(tmp)}"),
    ]


def plan_node_rtlcss() -> list[Command]:
    """Optional web toolchain for RTL/less asset compilation."""
    return [
        Command(tf("Install Node.js and npm"), "apt-get update && apt-get -y install nodejs npm"),
        Command(tf("Install rtlcss globally"), "npm install -g rtlcss"),
    ]


def plan_migration_clones(env: MigrationEnv, exists: Exists = _never) -> list[Command]:
    """Clone what each step needs, shallow, skipping clones already present.

    Every step needs its OpenUpgrade checkout. From 14 it also needs the matching
    Odoo clone, because the checkout is only an add-on collection; up to 13 the
    checkout *is* a full Odoo fork, so cloning Odoo separately would fetch a
    gigabyte nothing reads."""
    commands: list[Command] = []
    for version in env.chain():
        ou_dest = env.openupgrade_clone_dir(version)
        if not exists(ou_dest):
            commands.append(
                Command(
                    tf("Clone OpenUpgrade {}", version),
                    f"git clone --depth 1 --branch {shlex.quote(version)} --single-branch "
                    f"{shlex.quote(env.openupgrade_url)} {shlex.quote(str(ou_dest))}",
                )
            )
        if not env.uses_legacy_layout(version):
            odoo_dest = env.odoo_clone_dir(version)
            if not exists(odoo_dest):
                commands.append(
                    Command(
                        tf("Clone Odoo {}", version),
                        f"git clone --depth 1 --branch {shlex.quote(version)} --single-branch "
                        f"{shlex.quote(env.odoo_repo_url)} {shlex.quote(str(odoo_dest))}",
                    )
                )
    return commands


def _setuptools_pin(version: str) -> str:
    """The extra install argument a migration step needs, or an empty string.
    (Its 13.0 build pin lives in that step's constraints file instead.)"""
    return f" '{SETUPTOOLS_PIN}'" if odoo_major(version) <= PKG_RESOURCES_LAST_MAJOR else ""


def plan_migration_venvs(env: MigrationEnv, exists: Exists = _never) -> list[Command]:
    """For each natively-run version: write the overrides file, build a uv venv with
    the matched interpreter, and install requirements (with ``--overrides`` repairs)
    + psycopg2-binary + openupgradelib. Every step in the chain gets one.

    Skips on the ready *marker*, not the venv directory: a venv whose installs
    failed midway has no marker and is rebuilt (``uv venv`` recreates in place)."""
    commands: list[Command] = []
    for version in env.chain():
        python, _method = env.interpreter(version)
        if python is None:  # pragma: no cover - every version declares one
            continue
        if exists(env.venv_ready_marker(version)):
            continue
        if not commands:
            commands.append(
                Command(
                    tf("Create requirements directory"),
                    f"mkdir -p {shlex.quote(str(env.requirements_dir))}",
                )
            )
        venv = env.venv_dir(version)
        # For the <= 13 layout the OpenUpgrade checkout *is* Odoo, so its own
        # requirements.txt is the one to install; there is no separate clone.
        requirements = (
            env.openupgrade_clone_dir(version) if env.uses_legacy_layout(version)
            else env.odoo_clone_dir(version)
        ) / "requirements.txt"
        overrides = env.overrides_file(version)
        commands += write_text_file_command(
            overrides, templates.render_migration_overrides(version, python)
        )
        constraints_text = templates.render_migration_constraints(version)
        constraints = env.constraints_file(version)
        if constraints_text:
            commands += write_text_file_command(constraints, constraints_text)
        commands += [
            Command(
                tf("Create uv venv (Python {}) for Odoo {}", python, version),
                f"uv venv --clear --no-project --python {shlex.quote(python)} "
                f"{shlex.quote(str(venv))}",
            ),
            Command(
                tf("Install Odoo {} requirements", version),
                f"uv pip install --python {shlex.quote(str(venv))} "
                f"-r {shlex.quote(str(requirements))} "
                f"--overrides {shlex.quote(str(overrides))}"
                + (
                    f" --build-constraints {shlex.quote(str(constraints))}"
                    if constraints_text
                    else ""
                ),
            ),
            Command(
                tf("Install psycopg2-binary and openupgradelib for Odoo {}", version),
                f"uv pip install --python {shlex.quote(str(venv))} psycopg2-binary "
                f"openupgradelib{_setuptools_pin(version)}",
            ),
            Command(
                tf("Mark Odoo {} venv as ready", version),
                f"touch {shlex.quote(str(env.venv_ready_marker(version)))}",
            ),
        ]
    return commands


def plan_migration_configs(env: MigrationEnv) -> list[Command]:
    """Write the per-step odoo.conf and the run_migration.sh driver."""
    dirs: list[Path] = [env.conf_dir, env.checkpoints_dir, env.logs_dir, env.requirements_dir]
    for version in env.chain():
        dirs += [env.addons_custom_dir(version), env.addons_oca_dir(version)]
    commands: list[Command] = [
        Command(
            tf("Create migration directories"),
            "mkdir -p " + " ".join(shlex.quote(str(p)) for p in dirs),
        )
    ]
    for version in env.chain():
        commands += write_text_file_command(
            env.config_file(version), templates.render_migration_conf(env, version)
        )
    commands += write_text_file_command(
        env.root / "run_migration.sh", templates.render_run_migration_sh(env), "755"
    )
    return commands


def plan_generate_migration(env: MigrationEnv, exists: Exists = _never) -> list[Command]:
    """Full migration-environment plan: clones + uv venvs + configs + driver."""
    return (
        plan_migration_clones(env, exists)
        + plan_migration_venvs(env, exists)
        + plan_migration_configs(env)
    )


# Validated on WSL (2026-07-18): staged a sample module 16→18 (tree→list applied,
# version bumps, per-step logs). Pinned for reproducibility; bump deliberately.
STAGING_TOOL_SPEC = "odoo-module-migrator==0.5.0"


def plan_staging_tool(env: MigrationEnv) -> list[Command]:
    """Install `odoo-module-migrator` (OCA) into a shared uv tool venv — a host
    prerequisite prepared through the plan, never a runtime dependency of
    odoo_dwg."""
    venv = env.staging_tool_venv
    return [
        Command(
            tf("Create the staging tool venv"),
            f"uv venv --clear --no-project {shlex.quote(str(venv))}",
        ),
        Command(
            tf("Install odoo-module-migrator"),
            f"uv pip install --python {shlex.quote(str(venv))} {STAGING_TOOL_SPEC}",
        ),
    ]


def plan_stage_module(env: MigrationEnv, module: str, source_dir: Path) -> list[Command]:
    """Stage one custom module stepwise: the operator's source copy feeds the
    first step, each later step consumes the previous step's staged output, and
    `odoo-module-migrate` applies exactly that bump in place. The operator's
    source directory is never modified. Existing staged targets are replaced —
    the workflow gates that behind an exact-phrase confirmation."""
    migrate_bin = env.staging_tool_venv / "bin" / "odoo-module-migrate"
    commands: list[Command] = [
        Command(
            tf("Create staging directories for {}", module),
            "mkdir -p " + " ".join(
                shlex.quote(str(p))
                for p in [env.staging_dir] + [env.addons_custom_dir(v) for v in env.chain()]
            ),
        )
    ]
    previous = Path(source_dir) / module
    previous_version = env.source
    for version in env.chain():
        target_parent = env.addons_custom_dir(version)
        target = target_parent / module
        log = env.staging_log_file(module, version)
        commands += [
            Command(
                tf("Copy {} stage {} from the {} stage", module, version, previous_version),
                f"rm -rf {shlex.quote(str(target))} && "
                f"cp -a {shlex.quote(str(previous))} {shlex.quote(str(target_parent))}/",
            ),
            # odoo-module-migrate runs git commands over the directory (verified:
            # it fails with "not a git repository" otherwise), so each stage dir
            # is a throwaway git worktree with the pre-migration state committed.
            Command(
                tf("Prepare the git worktree for {} stage {}", module, version),
                f"git -C {shlex.quote(str(target_parent))} init -q && "
                f"git -C {shlex.quote(str(target_parent))} add -A && "
                f"git -C {shlex.quote(str(target_parent))} "
                f"-c user.name=odoo-dwg -c user.email=odoo-dwg@localhost "
                f"commit -qm {shlex.quote(f'stage {module} {version} input')} || true",
            ),
            Command(
                tf("Migrate {} code {} -> {}", module, previous_version, version),
                f"set -o pipefail && {shlex.quote(str(migrate_bin))} "
                f"--directory {shlex.quote(str(target_parent))} "
                f"--modules {shlex.quote(module)} "
                f"--init-version-name {shlex.quote(previous_version)} "
                f"--target-version-name {shlex.quote(version)} "
                f"2>&1 | tee {shlex.quote(str(log))}",
            ),
        ]
        previous = target
        previous_version = version
    return commands


def plan_clean_migration(root: Path, repos_dir: Path | None = None) -> list[Command]:
    """Remove one migration environment directory (venvs, confs, checkpoints, logs,
    requirements, driver). With ``repos_dir``, also remove the shared clones cache —
    note that cache serves every migration environment under the base directory.

    Destructive: the workflow gates this behind preview + an exact-phrase
    confirmation. The PostgreSQL migration database is host state, not files, and
    is deliberately not part of this plan."""
    commands = [
        Command(
            tf("Remove migration environment {}", str(root)),
            f"rm -rf {shlex.quote(str(root))}",
        )
    ]
    if repos_dir is not None:
        commands.append(
            Command(
                tf("Remove shared migration clones {}", str(repos_dir)),
                f"rm -rf {shlex.quote(str(repos_dir))}",
            )
        )
    return commands


def plan_refresh_repos(cfg: WorkspaceConfig, exists: Exists = _never) -> list[Command]:
    """Fast-forward-pull every present clone in the shared cache for this
    workspace's versions/OCA repos. Absent clones are skipped (nothing to refresh)."""
    commands: list[Command] = []
    for version in cfg.versions:
        dest = cfg.odoo_clone_dir(version)
        if exists(dest):
            commands.append(
                Command(
                    tf("Refresh Odoo {}", version),
                    f"git -C {shlex.quote(str(dest))} pull --ff-only",
                )
            )
    for repo in cfg.oca_repos:
        for version in cfg.versions:
            dest = cfg.oca_clone_dir(repo, version)
            if exists(dest):
                commands.append(
                    Command(
                        tf("Refresh OCA {} ({})", repo, version),
                        f"git -C {shlex.quote(str(dest))} pull --ff-only",
                    )
                )
    return commands


def plan_generate_workspace(
    cfg: WorkspaceConfig,
    exists: Exists = _never,
    interpreters: dict[str, InterpreterChoice] | None = None,
) -> list[Command]:
    """Full create plan: shared repo cache (skipping present clones), the workspace
    tree, then a venv build for each version whose venv is not already present. Pure
    — existence is injected; the workflow passes ``Path.exists`` and enforces the
    create-only guard (refusing to clobber an existing workspace).

    ``interpreters`` maps a version to the interpreter its venv must be built with
    (resolved against the support matrix by the workflow, which is what probes the
    host); versions absent from it use the host ``python3``."""
    commands = plan_repo_cache(cfg, exists)
    commands += plan_workspace_tree(cfg, interpreters)
    for version in cfg.versions:
        if not exists(cfg.venv_dir(version)):
            commands += plan_build_venv(
                cfg, version, interpreter=(interpreters or {}).get(version)
            )
    return commands


def plan_build_venv(
    cfg: WorkspaceConfig,
    version: str,
    recreate: bool = False,
    interpreter: InterpreterChoice | None = None,
) -> list[Command]:
    """Build one instance venv and install its version-matched requirements.

    ``recreate`` removes an existing venv first (management "regenerate"); by
    default it does not, so generation can skip versions whose venv already exists
    by simply not calling this.

    ``interpreter`` is the resolved choice for this version. A ``uv``-provided
    interpreter is created with ``uv venv --seed``, which seeds ``pip`` so every
    following step — and everything the generated workspace documents — is
    identical to a stdlib venv. Without it, the host ``python3`` is used.
    """
    venv = cfg.venv_dir(version)
    odoo = cfg.odoo_clone_dir(version)
    commands: list[Command] = []
    if recreate:
        commands.append(
            Command(tf("Remove existing venv {}", str(venv)), f"rm -rf {shlex.quote(str(venv))}")
        )
    if interpreter and interpreter.source == UV_PYTHON and interpreter.python:
        create = Command(
            tf("Create venv {} with uv (Python {})", str(venv), interpreter.python),
            f"uv venv --seed --no-project --python {shlex.quote(interpreter.python)} "
            f"{shlex.quote(str(venv))}",
        )
    else:
        create = Command(
            tf("Create venv {}", str(venv)),
            f"python3 -m venv {shlex.quote(str(venv))}",
        )
    commands += [
        create,
        Command(
            tf("Upgrade pip/wheel/setuptools in {}", str(venv)),
            f"{shlex.quote(str(venv / 'bin' / 'pip'))} install --upgrade pip wheel "
            f"{shlex.quote(setuptools_requirement(version))}",
        ),
        Command(
            tf("Install Odoo {} requirements", version),
            templates.requirements_install_command(
                str(venv / "bin" / "pip"), str(odoo / "requirements.txt"), version
            ),
        ),
    ]
    return commands
