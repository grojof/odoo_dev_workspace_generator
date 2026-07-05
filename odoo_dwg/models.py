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
    # Port assigned per instance is ``http_port_base + PORT_OFFSET_PER_MAJOR``.
    port_step: ClassVar[int] = 10

    name: str
    versions: list[str] = field(default_factory=lambda: ["18.0"])
    addon_prefix: str = ""
    http_port_base: int = 8069
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_user: str = ""

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
