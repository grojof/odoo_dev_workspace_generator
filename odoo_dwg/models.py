"""Domain model: workspaces, instances, and version facts.

Pure data + validation, no I/O and no execution (that lives in ``system``). A
``WorkspaceConfig`` is loaded from / saved to a JSON profile; everything derived
(paths, ports, per-version Python) is computed here so ``planners`` stay pure.

Version facts are anchored to official documentation — see ``docs/`` and the
plan's references appendix. Notably the *minimum* Python per Odoo major
(``ODOO_PYTHON_MINIMUM``) comes from the official "Source install" pages.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import ClassVar

# Workspace/client name: a short lowercase identifier reused for dirs, DB names,
# and instance names, so it must be filesystem- and PostgreSQL-safe.
WORKSPACE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

# First-class development versions (see the plan: dev on current majors).
SUPPORTED_DEV_VERSIONS: tuple[str, ...] = ("17.0", "18.0", "19.0")

# The OpenUpgrade migration chain runs one step per version, in order, no skips.
MIGRATION_CHAIN: tuple[str, ...] = (
    "12.0", "13.0", "14.0", "15.0", "16.0", "17.0", "18.0", "19.0",
)

# Minimum Python per Odoo major, from the official "Source install" pages
# (verbatim: 12→3.5, 13→3.6, 14→3.7, 17→3.10, 18→3.10). 15/16 track 3.7 as the
# documented floor (packaged against newer). This is the *floor*; the migration
# environment pairs a concrete interpreter per step (see docs/migration).
ODOO_PYTHON_MINIMUM: dict[int, str] = {
    12: "3.5", 13: "3.6", 14: "3.7", 15: "3.7",
    16: "3.7", 17: "3.10", 18: "3.10", 19: "3.10",
}


def odoo_major(version: str) -> int:
    """Parse the major from an Odoo version string (``18.0`` → ``18``)."""
    match = re.search(r"\d+", version or "")
    if not match:
        raise ValueError(f"Unparseable Odoo version: {version!r}")
    return int(match.group(0))


def python_minimum_for(version: str) -> str:
    """Documented minimum Python for an Odoo version (falls back to 3.10)."""
    return ODOO_PYTHON_MINIMUM.get(odoo_major(version), "3.10")


# Migration interpreter matrix — the Python and acquisition method per Odoo major.
# Measured on WSL Ubuntu 24.04: uv's installable floor is 3.8 (3.6/3.7 unavailable),
# so Odoo >= 14 runs natively via uv; Odoo 13 (Py 3.6) and 12 (Py 3.5) fall back to
# the official Docker images. Each step runs the *target* version, so only a chain
# that runs Odoo 13 (a 12->13 step) needs Docker.
MIGRATION_INTERPRETER: dict[int, tuple[str | None, str]] = {
    12: (None, "docker"),
    13: (None, "docker"),
    14: ("3.8", "uv"),
    15: ("3.8", "uv"),
    16: ("3.10", "uv"),
    17: ("3.10", "uv"),
    18: ("3.12", "uv"),
    19: ("3.12", "uv"),
}


def migration_interpreter(version: str) -> tuple[str | None, str]:
    """``(python, method)`` for running an Odoo version during migration —
    ``("3.8", "uv")`` for natives, ``(None, "docker")`` for 12/13."""
    return MIGRATION_INTERPRETER.get(odoo_major(version), ("3.12", "uv"))


def migration_chain(source: str, target: str) -> list[str]:
    """Ascending list of target versions from just-after ``source`` up to
    ``target`` (sequential, no skips), e.g. ``13.0``→``18.0`` ⇒ 14,15,16,17,18."""
    lo, hi = odoo_major(source), odoo_major(target)
    if lo >= hi:
        raise ValueError(f"source ({source}) must be older than target ({target}).")
    if lo < 12 or hi > 19:
        raise ValueError("migration is supported within the 12.0–19.0 range.")
    return [f"{major}.0" for major in range(lo + 1, hi + 1)]


@dataclass
class InstanceConfig:
    """A single Odoo version inside a workspace (its own venv, conf, and port)."""

    workspace: str
    version: str

    @property
    def major(self) -> int:
        return odoo_major(self.version)

    @property
    def name(self) -> str:
        """Instance name, e.g. workspace ``acme`` + ``18.0`` → ``odoo18acme``."""
        return f"odoo{self.major}{self.workspace}"

    @property
    def venv_name(self) -> str:
        return f"odoo{self.major}"

    @property
    def conf_name(self) -> str:
        return f"odoo{self.major}.conf"

    @property
    def python_minimum(self) -> str:
        return python_minimum_for(self.version)


@dataclass
class WorkspaceConfig:
    """A per-client development workspace described by a JSON profile."""

    # Base directory that holds every workspace and the shared repo cache.
    base_dir: ClassVar[str] = "~/odoo-workspaces"
    # Port assigned per instance is ``http_port_base + port_step`` per major.
    port_step: ClassVar[int] = 10
    # Upstream sources (official Odoo repo; OCA org for community addons).
    odoo_repo_url: ClassVar[str] = "https://github.com/odoo/odoo"
    oca_url_base: ClassVar[str] = "https://github.com/OCA"

    name: str
    versions: list[str] = field(default_factory=lambda: ["18.0"])
    addon_prefix: str = ""
    http_port_base: int = 8069
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_user: str = ""
    # OCA repository names (e.g. "web", "server-tools"), cloned per version and
    # symlinked into the workspace's ``addons-oca``. Empty by default — no
    # opinionated preset; fully profile-configurable.
    oca_repos: list[str] = field(default_factory=list)

    # --- derived ----------------------------------------------------------

    @property
    def root(self) -> Path:
        return Path(self.base_dir).expanduser() / self.name

    @property
    def repos_dir(self) -> Path:
        """Shared, read-only Odoo/OCA repo cache (one clone per version)."""
        return Path(self.base_dir).expanduser() / ".repos"

    def instances(self) -> list[InstanceConfig]:
        return [InstanceConfig(self.name, version) for version in self.versions]

    def http_port_for(self, version: str) -> int:
        """Deterministic per-version port: base + step per major above the lowest."""
        majors = sorted(odoo_major(v) for v in self.versions)
        offset = majors.index(odoo_major(version)) * self.port_step
        return self.http_port_base + offset

    # --- workspace tree paths --------------------------------------------

    @property
    def addons_custom_dir(self) -> Path:
        return self.root / "addons-custom"

    @property
    def addons_oca_dir(self) -> Path:
        return self.root / "addons-oca"

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def scripts_dir(self) -> Path:
        return self.root / "scripts"

    @property
    def vscode_dir(self) -> Path:
        return self.root / ".vscode"

    @property
    def code_workspace_file(self) -> Path:
        return self.root / f"{self.name}.code-workspace"

    @property
    def readme_file(self) -> Path:
        return self.root / "README.md"

    @property
    def profile_file(self) -> Path:
        """The saved profile marker inside the workspace, so it can be re-loaded
        for management."""
        return self.root / "workspace.json"

    def venv_dir(self, version: str) -> Path:
        return self.root / ".venv" / f"odoo{odoo_major(version)}"

    def config_file(self, version: str) -> Path:
        return self.config_dir / f"odoo{odoo_major(version)}.conf"

    # --- shared repo cache paths -----------------------------------------

    def odoo_clone_dir(self, version: str) -> Path:
        return self.repos_dir / f"odoo-{version}"

    def oca_clone_dir(self, repo: str, version: str) -> Path:
        return self.repos_dir / "oca" / f"{repo}-{version}"

    def oca_symlink_dir(self, repo: str, version: str) -> Path:
        """Per-version symlink under ``addons-oca`` pointing at the shared OCA
        checkout for that version — a stable, in-workspace path used in
        ``addons_path``. Per version because OCA addons must match the Odoo major."""
        return self.addons_oca_dir / f"odoo{odoo_major(version)}" / repo

    def addons_path(self, version: str) -> str:
        """Composed ``addons_path`` for a version, in precedence order: the
        workspace's custom addons, each configured OCA repo (via its in-workspace
        per-version symlink), then the shared Odoo ``addons``. All paths stay
        inside the workspace or the shared cache."""
        parts: list[Path] = [self.addons_custom_dir]
        parts += [self.oca_symlink_dir(repo, version) for repo in self.oca_repos]
        parts.append(self.odoo_clone_dir(version) / "addons")
        return ",".join(str(part) for part in parts)

    # --- normalization / validation --------------------------------------

    def normalize_defaults(self) -> None:
        if not self.db_user:
            self.db_user = self.name
        if not self.addon_prefix:
            self.addon_prefix = self.name
        # De-duplicate and order versions for stable port assignment.
        self.versions = sorted(set(self.versions), key=odoo_major)

    def validate(self) -> None:
        errors: list[str] = []
        if not WORKSPACE_NAME_RE.fullmatch(self.name):
            errors.append(
                "invalid workspace name: start with a lowercase letter, "
                "only [a-z0-9_], max 32 chars."
            )
        if not self.versions:
            errors.append("at least one Odoo version is required.")
        for version in self.versions:
            try:
                odoo_major(version)
            except ValueError:
                errors.append(f"invalid Odoo version: {version!r} (expected e.g. 18.0).")
        if errors:
            raise ValueError(" ".join(errors))

    # --- JSON round-trip --------------------------------------------------

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n"

    def save(self, path: str | Path) -> None:
        Path(path).expanduser().write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict) -> WorkspaceConfig:
        """Build a config from a parsed JSON dict, ignoring unknown keys so old
        profiles keep loading (forward-compatible)."""
        known = {f for f in cls.__dataclass_fields__}  # noqa: C416
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def load(cls, path: str | Path) -> WorkspaceConfig:
        data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
        return cls.from_dict(data)


@dataclass
class MigrationEnv:
    """An OpenUpgrade migration environment for a ``source`` → ``target`` chain."""

    base_dir: ClassVar[str] = "~/odoo-migrations"
    odoo_repo_url: ClassVar[str] = "https://github.com/odoo/odoo"
    openupgrade_url: ClassVar[str] = "https://github.com/OCA/OpenUpgrade"

    source: str
    target: str
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_user: str = "odoo"
    working_db: str = "migration"

    # --- derived ----------------------------------------------------------

    @property
    def root(self) -> Path:
        return Path(self.base_dir).expanduser() / f"{odoo_major(self.source)}-to-{odoo_major(self.target)}"

    @property
    def repos_dir(self) -> Path:
        return Path(self.base_dir).expanduser() / ".repos"

    @property
    def conf_dir(self) -> Path:
        return self.root / "conf"

    @property
    def checkpoints_dir(self) -> Path:
        return self.root / "checkpoints"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def requirements_dir(self) -> Path:
        return self.root / "requirements"

    def chain(self) -> list[str]:
        return migration_chain(self.source, self.target)

    def interpreter(self, version: str) -> tuple[str | None, str]:
        return migration_interpreter(version)

    def is_native(self, version: str) -> bool:
        return self.interpreter(version)[1] == "uv"

    def odoo_clone_dir(self, version: str) -> Path:
        return self.repos_dir / f"odoo-{version}"

    def openupgrade_clone_dir(self, version: str) -> Path:
        return self.repos_dir / f"openupgrade-{version}"

    def venv_dir(self, version: str) -> Path:
        return self.root / ".venv" / f"odoo{odoo_major(version)}"

    def venv_ready_marker(self, version: str) -> Path:
        """Written after a venv's installs finish; its absence means the venv is
        missing *or* half-built and must be (re)built on the next generation."""
        return self.venv_dir(version) / ".odwg-ready"

    def overrides_file(self, version: str) -> Path:
        return self.requirements_dir / f"overrides-{version}.txt"

    def config_file(self, version: str) -> Path:
        return self.conf_dir / f"odoo{odoo_major(version)}.conf"

    def upgrade_scripts_dir(self, version: str) -> Path:
        """OpenUpgrade scripts path (>= 14.0 module layout)."""
        return self.openupgrade_clone_dir(version) / "openupgrade_scripts" / "scripts"

    def addons_path(self, version: str) -> str:
        odoo = self.odoo_clone_dir(version)
        ou = self.openupgrade_clone_dir(version)
        return ",".join(str(p) for p in (odoo / "addons", odoo / "odoo" / "addons", ou / "openupgrade_scripts"))

    def needs_docker(self) -> bool:
        return any(not self.is_native(v) for v in self.chain())

    def validate(self) -> None:
        # migration_chain enforces source < target and the 12–19 range.
        self.chain()
