"""Domain model: workspaces, instances, and version facts.

Pure data + validation, no I/O and no execution (that lives in ``system``). A
``WorkspaceConfig`` is loaded from / saved to a JSON profile; everything derived
(paths, ports, per-version Python) is computed here so ``planners`` stay pure.

Version facts live in one authoritative support matrix (``ODOO_SUPPORT`` plus
``SUPPORTED_HOSTS``), where every bound carries the evidence behind it. See
``docs/support-matrix.md`` for the sources and the procedure that re-derives
them.
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

# The development PostgreSQL role shared by workspaces and migration environments,
# and the one `provision apply` creates by default. Loopback auth is `trust`, so a
# role per workspace would isolate nothing and only need another `sudo` step.
DEFAULT_DB_ROLE = "odoo"
# A role is interpolated into SQL and written through shell heredocs, so only a
# plain unquoted identifier is accepted (lowercase: unquoted names fold to it;
# 63 bytes: NAMEDATALEN - 1).
DB_ROLE_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
# A database name as Odoo's own database manager accepts it (DBNAME_PATTERN in
# addons/web/controllers/main.py on 14, database.py on 19).
DB_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]+$")

# An Odoo module (add-on) directory name: a Python identifier, as Odoo imports it.
MODULE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,63}$")
# An OCA repository name as it appears in github.com/OCA/<repo>: never a path.
OCA_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
# A PostgreSQL host: a DNS name or an IPv4/IPv6 literal, nothing a shell or an
# odoo.conf line could misread.
DB_HOST_RE = re.compile(r"^([A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?|[0-9A-Fa-f:.]{2,45})$")

# OpenUpgrade changed layout at 14: up to 13 the checkout is a full Odoo fork
# whose migration scripts live inside each add-on; from 14 it is an add-on
# collection with scripts under openupgrade_scripts/scripts.
LEGACY_LAYOUT_MAX_MAJOR = 13

# The OpenUpgrade migration chain runs one step per version, in order, no skips.
MIGRATION_CHAIN: tuple[str, ...] = (
    "12.0", "13.0", "14.0", "15.0", "16.0", "17.0", "18.0", "19.0",
)


def version_error(version: object) -> str | None:
    """Why ``version`` is not a supported Odoo version string, or None.

    Exactly one of the chain's ``NN.0`` strings: a version ends up in paths,
    generated scripts and ``odoo.conf``, so anything looser (``18``,
    ``18.0$(…)``) is refused here rather than quoted everywhere downstream."""
    if isinstance(version, str) and version in MIGRATION_CHAIN:
        return None
    return f"invalid Odoo version: {version!r} (supported: {', '.join(MIGRATION_CHAIN)})."


def _port_error(label: str, value: object, highest: int = 65535) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= highest:
        return None
    return f"invalid {label}: {value!r} (a whole number from 1 to {highest})."

def odoo_major(version: str) -> int:
    """Parse the major from an Odoo version string (``18.0`` → ``18``)."""
    match = re.search(r"\d+", version or "")
    if not match:
        raise ValueError(f"Unparseable Odoo version: {version!r}")
    return int(match.group(0))


# Odoo <= 16 imports ``pkg_resources`` at startup (odoo/modules/module.py), which
# setuptools removed in 81. Which setuptools a venv ends up with depends on the
# interpreter: Python 3.8 resolves 75.x and works by luck, while 3.10+ resolves
# 81+ and Odoo dies with ModuleNotFoundError before it starts. Every venv built for
# such a version — workspace or migration — pins it; setuptools itself recommends
# "pin to Setuptools<81" for pkg_resources users.
PKG_RESOURCES_LAST_MAJOR = 16
SETUPTOOLS_PIN = "setuptools<81"
# Odoo <= 13 requires ``vatnumber==1.2``, whose setup.py still passes ``use_2to3``,
# which setuptools removed in 58; it builds against the venv's own setuptools.
USE_2TO3_LAST_MAJOR = 13
SETUPTOOLS_2TO3_PIN = "setuptools<58"


def setuptools_requirement(version: str) -> str:
    """The setuptools requirement a workspace venv for ``version`` installs."""
    major = odoo_major(version)
    if major <= USE_2TO3_LAST_MAJOR:
        return SETUPTOOLS_2TO3_PIN
    if major <= PKG_RESOURCES_LAST_MAJOR:
        return SETUPTOOLS_PIN
    return "setuptools"


# Requirements a workspace venv installs in place of one its Odoo branch pins,
# as ``{major: (dropped project, replacement requirement)}``. Odoo 12 pins
# ``pyldap==2.4.28``, a fork PyPI marks "DEPRECATED; use python-ldap instead"
# (merged back as python-ldap 3.0) that does not build on uv's Python 3.8: its
# setup.py passes runtime_library_dirs, which distutils renders as ``-R`` for
# that interpreter's ``cc``. python-ldap 3.1.0 is what Odoo 13 pins for the same
# ``ldap`` module.
REQUIREMENT_SUBSTITUTES: dict[int, tuple[str, str]] = {
    12: ("pyldap", "python-ldap==3.1.0"),
}


def requirement_substitute(version: str) -> tuple[str, str] | None:
    """``(dropped project, replacement)`` for a version's requirements, if any."""
    return REQUIREMENT_SUBSTITUTES.get(odoo_major(version))


# An interpreter an operator may name: CPython 3.N, as uv and the venv tools take it.
PYTHON_VERSION_RE = re.compile(r"^3\.[0-9]{1,2}$")


def python_version_error(python: object) -> str | None:
    """Why ``python`` is not a ``3.N`` interpreter version, or None."""
    if isinstance(python, str) and PYTHON_VERSION_RE.fullmatch(python):
        return None
    return f"invalid Python version: {python!r} (expected e.g. 3.10)."


def python_tuple(python: str) -> tuple[int, ...]:
    """``"3.10"`` → ``(3, 10)``, so Python versions compare numerically rather
    than as strings (where ``"3.9" > "3.10"``)."""
    try:
        return tuple(int(part) for part in str(python).split(".") if part != "")
    except ValueError as exc:
        raise ValueError(f"Unparseable Python version: {python!r}") from exc


# --- support matrix ---------------------------------------------------------
# The single authoritative declaration of what this tool supports. Every
# operator-facing surface reads its bounds from here and none restates them, so
# changing a bound here changes every surface. Each bound carries the evidence
# backing it, because only Odoo 19 states a Python *maximum* outright: the rest
# are derived from each branch's own requirements, and output must never pass a
# derived bound off as an official Odoo requirement.
#
# The sources, their precedence and the procedure that re-derives them live in
# docs/support-matrix.md; tools/verify_support_matrix.py checks this data
# against them.

OFFICIAL = "official"  # stated outright by Odoo or by the distribution
DERIVED = "derived"    # deduced from an official artifact (e.g. requirements.txt)
UNTESTED = "untested"  # no source states it and this project has not validated it

EVIDENCE_TIERS: tuple[str, ...] = (OFFICIAL, DERIVED, UNTESTED)

# Source URL shapes. The documentation layout changed twice across the supported
# range, which is why the era is resolved rather than assumed — and why the
# repository, not the manual, is the primary source (13.0's page is a stub).
ODOO_SETUP_PY_URL = "https://raw.githubusercontent.com/odoo/odoo/{version}/setup.py"
ODOO_RELEASE_PY_URL = "https://raw.githubusercontent.com/odoo/odoo/{version}/odoo/release.py"
ODOO_REQUIREMENTS_URL = "https://raw.githubusercontent.com/odoo/odoo/{version}/requirements.txt"
_DOCS_SETUP_ERA = "https://www.odoo.com/documentation/{version}/setup/install.html"
_DOCS_INSTALL_ERA = "https://www.odoo.com/documentation/{version}/administration/install/source.html"
_DOCS_ON_PREMISE_ERA = (
    "https://www.odoo.com/documentation/{version}/administration/on_premise/source.html"
)


def odoo_docs_url(version: str) -> str:
    """The official source-install page for an Odoo version, picking the URL
    layout of its era (12/13, 14, then 15+)."""
    major = odoo_major(version)
    if major <= 13:
        template = _DOCS_SETUP_ERA
    elif major == 14:
        template = _DOCS_INSTALL_ERA
    else:
        template = _DOCS_ON_PREMISE_ERA
    return template.format(version=version)


@dataclass(frozen=True)
class Bound:
    """A support bound plus the evidence behind it. ``value is None`` means no
    source states the bound at all (tier ``untested``)."""

    value: str | None
    tier: str
    source: str

    @property
    def is_official(self) -> bool:
        return self.tier == OFFICIAL

    def describe(self) -> str:
        """Operator-facing text. A derived or untested bound always says so, so
        it cannot read as something Odoo requires."""
        if self.value is None:
            return f"not stated — {self.source}"
        if self.tier == OFFICIAL:
            return self.value
        return f"{self.value} ({self.tier}: {self.source})"


@dataclass(frozen=True)
class VersionSupport:
    """What the project supports for one Odoo version: the Python range Odoo
    declares (or that its own requirements imply), the interpreter this project
    recommends and has built with, and the PostgreSQL floor."""

    version: str
    python_min: Bound
    python_max: Bound
    postgres_min: Bound
    recommended_python: str | None
    acquisition: str  # "uv" — every version runs on a uv-provided interpreter

    @property
    def major(self) -> int:
        return odoo_major(self.version)

    @property
    def is_native(self) -> bool:
        return self.acquisition == "uv"

    def python_range_text(self) -> str:
        """e.g. ``3.10 – 3.14 (official)`` or ``3.7 – 3.12 (derived: …)``."""
        upper = self.python_max.describe() if self.python_max.value else "no maximum stated"
        return f"{self.python_min.describe()} – {upper}"

    def python_in_range(self, python: str) -> bool:
        """Whether a concrete interpreter falls inside the declared range. An
        unstated maximum bounds nothing, so only the floor applies."""
        candidate = python_tuple(python)
        if self.python_min.value and candidate < python_tuple(self.python_min.value):
            return False
        if self.python_max.value and candidate > python_tuple(self.python_max.value):
            return False
        return True


def _official_docs(version: str) -> str:
    return f"Odoo {version} source install — {odoo_docs_url(version)}"


def _official_setup(version: str) -> str:
    return f"odoo/odoo@{version} setup.py python_requires"


def _derived_requirements(version: str, distro: str) -> str:
    return (
        f"odoo/odoo@{version} requirements.txt — newest interpreter bucket targets {distro}"
    )


# Python minima are the documented floors (all confirmed against each branch's
# setup.py). Maxima come from the newest interpreter bucket each branch's
# requirements.txt declares, read through the distribution its comment names —
# a derivation that reproduces Odoo 19's own MAX_PY_VERSION exactly, which is
# what makes it trustworthy for the versions that state nothing. Recommended
# interpreters are the ones this project has actually built and run (measured on
# WSL Ubuntu 24.04, where uv's installable floor is 3.8), so they are inside the
# range but not always at its top.
ODOO_SUPPORT: dict[int, VersionSupport] = {
    12: VersionSupport(
        version="12.0",
        python_min=Bound("3.5", OFFICIAL, _official_docs("12.0")),
        python_max=Bound(None, UNTESTED, "no requirements bucket names a distribution"),
        postgres_min=Bound(None, UNTESTED, 'docs say only "the latest version of PostgreSQL"'),
        # Nominal: no chain ever runs Odoo 12 (it is the database's starting
        # point, restored and migrated away from), so this is never exercised.
        recommended_python="3.8",
        acquisition="uv",
    ),
    13: VersionSupport(
        version="13.0",
        python_min=Bound("3.6", OFFICIAL, _official_setup("13.0")),
        python_max=Bound(None, UNTESTED, "no requirements bucket names a distribution"),
        postgres_min=Bound(None, UNTESTED, "the 13.0 install page states no floor"),
        # Above its documented 3.6 floor, but uv's floor is 3.8 and the branch's
        # requirements install and run there (measured on WSL, 2026-09-17), which
        # is what lets this step run natively instead of in a container.
        recommended_python="3.8",
        acquisition="uv",
    ),
    14: VersionSupport(
        version="14.0",
        # The docs say 3.7 while setup.py declares >=3.6; the stricter,
        # documented floor is the one carried here.
        python_min=Bound("3.7", OFFICIAL, _official_docs("14.0") + " (setup.py says >=3.6)"),
        python_max=Bound("3.10", DERIVED, _derived_requirements("14.0", "Ubuntu 22.04 Jammy")),
        postgres_min=Bound("12.0", OFFICIAL, _official_docs("14.0")),
        recommended_python="3.8",
        acquisition="uv",
    ),
    15: VersionSupport(
        version="15.0",
        python_min=Bound("3.7", OFFICIAL, _official_docs("15.0")),
        python_max=Bound("3.12", DERIVED, _derived_requirements("15.0", "Ubuntu 24.04 Noble")),
        postgres_min=Bound("12.0", OFFICIAL, _official_docs("15.0")),
        recommended_python="3.8",
        acquisition="uv",
    ),
    16: VersionSupport(
        version="16.0",
        python_min=Bound("3.7", OFFICIAL, _official_docs("16.0")),
        python_max=Bound("3.13", DERIVED, _derived_requirements("16.0", "Debian 13 Trixie")),
        postgres_min=Bound("12.0", OFFICIAL, _official_docs("16.0")),
        recommended_python="3.10",
        acquisition="uv",
    ),
    17: VersionSupport(
        version="17.0",
        python_min=Bound("3.10", OFFICIAL, _official_docs("17.0")),
        python_max=Bound("3.14", DERIVED, _derived_requirements("17.0", "Ubuntu 26.04 Resolute")),
        postgres_min=Bound("12.0", OFFICIAL, _official_docs("17.0")),
        recommended_python="3.10",
        acquisition="uv",
    ),
    18: VersionSupport(
        version="18.0",
        python_min=Bound("3.10", OFFICIAL, _official_docs("18.0")),
        python_max=Bound("3.14", DERIVED, _derived_requirements("18.0", "Ubuntu 26.04 Resolute")),
        postgres_min=Bound("12.0", OFFICIAL, _official_docs("18.0")),
        recommended_python="3.12",
        acquisition="uv",
    ),
    19: VersionSupport(
        version="19.0",
        python_min=Bound("3.10", OFFICIAL, "odoo/odoo@19.0 odoo/release.py MIN_PY_VERSION"),
        # The one version that declares a maximum outright — and it agrees with
        # the requirements-bucket derivation used for 14–18.
        python_max=Bound("3.14", OFFICIAL, "odoo/odoo@19.0 odoo/release.py MAX_PY_VERSION"),
        postgres_min=Bound("13.0", OFFICIAL, _official_docs("19.0")),
        recommended_python="3.12",
        acquisition="uv",
    ),
}


@dataclass(frozen=True)
class HostSupport:
    """A Linux host release this project supports, with the facts that follow
    from the release (its system Python and PostgreSQL major)."""

    name: str
    os_id: str
    version_id: str
    codename: str
    system_python: str
    postgres_major: str
    reference: bool = False


# One host, and only one: the release every end-to-end acceptance runs on.
# Debian and then Ubuntu 22.04 were dropped rather than implying support that
# was never validated. The row's system Python and PostgreSQL come from
# packages.ubuntu.com for that codename.
SUPPORTED_HOSTS: tuple[HostSupport, ...] = (
    HostSupport("Ubuntu 24.04 LTS", "ubuntu", "24.04", "noble", "3.12", "16", reference=True),
)

# The tool's own floor: the supported host's system Python. Kept in step with
# ``requires-python`` in pyproject.toml.
TOOL_PYTHON_MINIMUM = "3.12"


def supported_host(os_id: str, version_id: str) -> HostSupport | None:
    """The matching supported host release, or ``None`` when the host is not one
    this project supports."""
    for host in SUPPORTED_HOSTS:
        if host.os_id == (os_id or "").lower() and host.version_id == (version_id or ""):
            return host
    return None


def supported_hosts_text() -> str:
    return " / ".join(host.name for host in SUPPORTED_HOSTS)


def version_support(version: str) -> VersionSupport:
    """The matrix row for an Odoo version. Raises for a version outside the
    matrix rather than guessing a bound for it."""
    major = odoo_major(version)
    support = ODOO_SUPPORT.get(major)
    if support is None:
        supported = ", ".join(str(v) for v in sorted(ODOO_SUPPORT))
        raise ValueError(f"Unsupported Odoo version: {version} (supported majors: {supported}).")
    return support


def version_support_or_none(version: str) -> VersionSupport | None:
    """Like ``version_support`` but returns ``None`` instead of raising, for
    surfaces that report an unsupported version rather than failing on it."""
    try:
        return version_support(version)
    except ValueError:
        return None


def python_minimum_for(version: str) -> str:
    """Documented minimum Python for an Odoo version."""
    minimum = version_support(version).python_min.value
    # Every row in the matrix declares a floor; guard so a future gap is loud.
    if minimum is None:
        raise ValueError(f"No Python minimum declared for Odoo {version}.")
    return minimum


def python_maximum_for(version: str) -> str | None:
    """Maximum Python for an Odoo version, or ``None`` when no source states
    one. Check ``version_support(version).python_max.tier`` before presenting
    it: only Odoo 19 declares its maximum officially."""
    return version_support(version).python_max.value


def python_in_range(version: str, python: str) -> bool:
    """Whether an interpreter falls inside an Odoo version's declared range."""
    return version_support(version).python_in_range(python)


def postgres_minimum_for(version: str) -> str | None:
    """Minimum PostgreSQL for an Odoo version, or ``None`` when not stated."""
    return version_support(version).postgres_min.value


def postgres_floor_for(versions: list[str] | tuple[str, ...]) -> tuple[str, str] | None:
    """The highest PostgreSQL floor across several Odoo versions, as
    ``(floor, version requiring it)`` — what a single shared server must meet.
    ``None`` when none of them states a floor."""
    floors = [
        (support.postgres_min.value, support.version)
        for support in (version_support_or_none(v) for v in versions)
        if support is not None and support.postgres_min.value
    ]
    if not floors:
        return None
    floor, version = max(floors, key=lambda item: python_tuple(item[0]))
    return floor, version


# Interpreter sources: where the Python running an Odoo version comes from.
HOST_PYTHON = "host"  # the host's own python3
UV_PYTHON = "uv"      # an interpreter uv provides


@dataclass(frozen=True)
class InterpreterChoice:
    """The interpreter an environment will be built with, and whether that
    crosses one of the version's declared bounds. Pure derivation: deciding is
    separate from probing the host and from running anything."""

    version: str
    python: str | None
    source: str
    out_of_range: bool = False
    crossed: Bound | None = None

    @property
    def needs_uv(self) -> bool:
        return self.source == UV_PYTHON

    def describe(self) -> str:
        label = f"{self.python} ({self.source})"
        if self.out_of_range:
            return f"{label} — outside the supported range"
        return label


def resolve_interpreter(
    version: str,
    host_python: str | None = None,
    operator_choice: str | None = None,
) -> InterpreterChoice:
    """Decide which interpreter builds an Odoo version's environment.

    The host ``python3`` wins whenever it is inside the version's declared range,
    so nothing changes for the common case. Outside the range, the matrix's
    recommendation is offered instead (provisioned by ``uv``). A range with no
    stated maximum (Odoo 12/13) is no evidence that a newer host works — on 3.12
    their pinned ``gevent`` does not even build — so there the host is the default
    only up to the recommendation. An
    ``operator_choice`` always takes precedence — that is how a migration is
    rehearsed on the exact Python a client runs — and is reported, not silently
    accepted, when it falls outside the range.
    """
    support = version_support(version)
    if operator_choice:
        chosen = operator_choice
        source = HOST_PYTHON if host_python and chosen == host_python else UV_PYTHON
    elif host_python and _host_is_a_safe_default(support, host_python):
        chosen, source = host_python, HOST_PYTHON
    elif support.recommended_python:
        chosen, source = support.recommended_python, UV_PYTHON
    else:  # pragma: no cover - every native row recommends an interpreter
        chosen, source = host_python or "", HOST_PYTHON

    in_range = support.python_in_range(chosen)
    return InterpreterChoice(
        support.version,
        chosen,
        source,
        out_of_range=not in_range,
        crossed=None if in_range else _crossed_bound(support, chosen),
    )


def interpreter_from_pyvenv(version: str, pyvenv_cfg: str) -> InterpreterChoice | None:
    """The interpreter an existing venv was built with, read from its
    ``pyvenv.cfg``: ``uv`` writes a ``uv = <version>`` key and ``version_info``,
    the stdlib ``venv`` writes ``version``. ``None`` when it cannot be told."""
    keys: dict[str, str] = {}
    for line in pyvenv_cfg.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            keys[key.strip()] = value.strip()
    match = re.match(r"(\d+\.\d+)", keys.get("version_info") or keys.get("version", ""))
    if not match:
        return None
    python = match.group(1)
    source = UV_PYTHON if "uv" in keys else HOST_PYTHON
    support = version_support(version)
    in_range = support.python_in_range(python)
    return InterpreterChoice(
        support.version,
        python,
        source,
        out_of_range=not in_range,
        crossed=None if in_range else _crossed_bound(support, python),
    )


def _host_is_a_safe_default(support: VersionSupport, host_python: str) -> bool:
    """In range, and — when no maximum is stated — no newer than the recommendation."""
    if not support.python_in_range(host_python):
        return False
    if support.python_max.value or not support.recommended_python:
        return True
    return python_tuple(host_python) <= python_tuple(support.recommended_python)


def _crossed_bound(support: VersionSupport, python: str) -> Bound | None:
    """Which declared bound a chosen interpreter falls outside of."""
    candidate = python_tuple(python)
    if support.python_max.value and candidate > python_tuple(support.python_max.value):
        return support.python_max
    if support.python_min.value and candidate < python_tuple(support.python_min.value):
        return support.python_min
    return None


def migration_interpreter(version: str) -> tuple[str | None, str]:
    """``(python, method)`` for running an Odoo version during migration —
    e.g. ``("3.8", "uv")``. The Python is the matrix's recommendation for that
    version."""
    support = version_support(version)
    return support.recommended_python, support.acquisition


def migration_chain(source: str, target: str) -> list[str]:
    """Ascending list of target versions from just-after ``source`` up to
    ``target`` (sequential, no skips), e.g. ``13.0``→``18.0`` ⇒ 14,15,16,17,18."""
    for version in (source, target):
        error = version_error(version)
        if error:
            raise ValueError(error)
    lo, hi = odoo_major(source), odoo_major(target)
    if lo >= hi:
        raise ValueError(f"source ({source}) must be older than target ({target}).")
    if lo < 12 or hi > 19:
        raise ValueError("migration is supported within the 12.0–19.0 range.")
    return [f"{major}.0" for major in range(lo + 1, hi + 1)]


@dataclass
class Command:
    """One step of a plan: what it does, and the shell command that does it.
    Planners build these (pure); only ``system`` runs them."""

    description: str
    command: str


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
    def odools_file(self) -> Path:
        """The official Odoo language server's configuration, at the workspace
        root where OdooLS looks for it."""
        return self.root / "odools.toml"

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

    def addons_dirs(self, version: str, include_core: bool = True) -> list[Path]:
        """The add-on directories for a version, in precedence order: the
        workspace's custom addons, each configured OCA repo (via its in-workspace
        per-version symlink), then — unless ``include_core`` is false — the shared
        Odoo ``addons``. All paths stay inside the workspace or the shared cache.

        ``include_core=False`` is what a tool that loads core from the Odoo source
        itself needs (the OdooLS ``odools.toml``); both views come from this one
        list, so they cannot disagree."""
        parts: list[Path] = [self.addons_custom_dir]
        parts += [self.oca_symlink_dir(repo, version) for repo in self.oca_repos]
        if include_core:
            parts.append(self.odoo_clone_dir(version) / "addons")
        return parts

    def addons_path(self, version: str) -> str:
        """Composed ``addons_path`` for a version's ``odoo.conf``."""
        return ",".join(str(part) for part in self.addons_dirs(version))

    # --- normalization / validation --------------------------------------

    def normalize_defaults(self) -> None:
        if not self.db_user:
            self.db_user = DEFAULT_DB_ROLE
        # De-duplicate and order versions for stable port assignment. Malformed
        # values are left for validate() to report, not raised here.
        if isinstance(self.versions, list) and all(
            version_error(v) is None for v in self.versions
        ):
            self.versions = sorted(set(self.versions), key=odoo_major)

    def validate(self) -> None:
        errors: list[str] = []
        if not (isinstance(self.name, str) and WORKSPACE_NAME_RE.fullmatch(self.name)):
            errors.append(
                "invalid workspace name: start with a lowercase letter, "
                "only [a-z0-9_], max 32 chars."
            )
        if not (isinstance(self.db_user, str) and DB_ROLE_RE.fullmatch(self.db_user)):
            errors.append(
                f"invalid db_user: {self.db_user!r} (a PostgreSQL role: lowercase letters, "
                "digits and underscores, max 63 chars)."
            )
        if not isinstance(self.versions, list) or not self.versions:
            errors.append("at least one Odoo version is required.")
        else:
            errors += [e for e in map(version_error, self.versions) if e]
        if not isinstance(self.oca_repos, list):
            errors.append("oca_repos must be a list of OCA repository names.")
        else:
            errors += [
                f"invalid OCA repository name: {repo!r}."
                for repo in self.oca_repos
                if not (isinstance(repo, str) and OCA_REPO_RE.fullmatch(repo) and ".." not in repo)
            ]
        if not (isinstance(self.db_host, str) and DB_HOST_RE.fullmatch(self.db_host)):
            errors.append(f"invalid db_host: {self.db_host!r} (a host name or IP address).")
        # The highest instance port plus the bus offset (+1000) must stay valid.
        errors += [e for e in (_port_error("db_port", self.db_port),
                               _port_error("http_port_base", self.http_port_base, 64000)) if e]
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
        if not isinstance(data, dict):
            raise ValueError(f"a workspace profile must be a JSON object, not {type(data).__name__}.")
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
    db_user: str = DEFAULT_DB_ROLE
    working_db: str = "migration"
    # Per-step interpreter overrides, ``{version: python}``. Empty means every
    # step uses the matrix's recommendation. An override exists so a migration
    # can be rehearsed on the exact Python a client runs.
    interpreter_overrides: dict[str, str] = field(default_factory=dict)

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

    def interpreter_choice(self, version: str) -> InterpreterChoice:
        """The resolved interpreter for one chain step, applying an override when
        the operator set one. Migration venvs are always ``uv``-provided, so the
        host ``python3`` is deliberately not offered here."""
        return resolve_interpreter(
            version,
            host_python=None,
            operator_choice=self.interpreter_overrides.get(version),
        )

    def interpreter(self, version: str) -> tuple[str | None, str]:
        """``(python, method)`` for a chain step — the override if one is set,
        otherwise the matrix's recommendation."""
        choice = self.interpreter_choice(version)
        return choice.python, choice.source

    def set_interpreter_override(self, version: str, python: str) -> InterpreterChoice:
        """Pin one chain step to an interpreter. Refuses a version outside the
        chain. Returns the resolved choice, which reports whether it is out of
        range."""
        chain = self.chain()
        if version not in chain:
            raise ValueError(f"{version} is not a step in this chain ({', '.join(chain)}).")
        error = python_version_error(python)
        if error:
            raise ValueError(error)
        choice = resolve_interpreter(version, operator_choice=python)
        self.interpreter_overrides[version] = python
        return choice

    def clear_interpreter_override(self, version: str) -> None:
        self.interpreter_overrides.pop(version, None)

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

    @property
    def tools_dir(self) -> Path:
        """Shared tool venvs (one per host tool), serving every environment."""
        return Path(self.base_dir).expanduser() / ".tools"

    @property
    def staging_tool_venv(self) -> Path:
        return self.tools_dir / "module-migrator"

    @property
    def staging_dir(self) -> Path:
        return self.root / "staging"

    def staging_log_file(self, module: str, version: str) -> Path:
        return self.staging_dir / f"log-{module}-{version}.txt"

    def staging_report_file(self, module: str) -> Path:
        return self.staging_dir / f"report-{module}.md"

    def config_file(self, version: str) -> Path:
        return self.conf_dir / f"odoo{odoo_major(version)}.conf"

    def upgrade_scripts_dir(self, version: str) -> Path:
        """OpenUpgrade scripts path (>= 14.0 module layout)."""
        return self.openupgrade_clone_dir(version) / "openupgrade_scripts" / "scripts"

    def addons_custom_dir(self, version: str) -> Path:
        """Where the operator places each custom module's *migrated branch* for
        this target version (populated by hand or by the staging workflow)."""
        return self.root / "addons" / f"odoo{odoo_major(version)}" / "custom"

    def addons_oca_dir(self, version: str) -> Path:
        return self.root / "addons" / f"odoo{odoo_major(version)}" / "oca"

    def addons_path(self, version: str) -> str:
        """Operator code first (custom → OCA — first match wins in Odoo's module
        lookup), then the OpenUpgrade checkout, then core.

        Two layouts. For Odoo >= 14 the checkout is an add-on collection beside a
        separate Odoo clone, and its *root* is listed so ``openupgrade_framework``
        and ``openupgrade_scripts`` both resolve. For Odoo <= 13 the checkout *is*
        Odoo (a full fork) and every migration script lives inside its own add-on,
        so the path names the fork's ``addons`` directory — listing anything else
        leaves those scripts unreachable and the step silently skips them."""
        openupgrade = self.openupgrade_clone_dir(version)
        if odoo_major(version) <= LEGACY_LAYOUT_MAX_MAJOR:
            parts = (
                self.addons_custom_dir(version),
                self.addons_oca_dir(version),
                openupgrade / "addons",
            )
        else:
            odoo = self.odoo_clone_dir(version)
            parts = (
                self.addons_custom_dir(version),
                self.addons_oca_dir(version),
                openupgrade,
                odoo / "addons",
                odoo / "odoo" / "addons",
            )
        return ",".join(str(p) for p in parts)

    def coverage_dirs(self, version: str) -> list[Path]:
        """Every directory a step resolves modules from, in lookup order: its
        ``addons_path`` plus the core add-ons ``odoo-bin`` always adds itself
        (``<odoo>/odoo/addons``). For a <= 13 step that is the fork's own
        ``odoo/addons``, where ``base`` lives; no separate Odoo clone exists."""
        dirs = [Path(part) for part in self.addons_path(version).split(",")]
        if self.uses_legacy_layout(version):
            dirs.append(self.openupgrade_clone_dir(version) / "odoo" / "addons")
        return dirs

    def apriori_file(self, version: str) -> Path:
        """Where a step's OpenUpgrade declares module renames and merges: inside
        ``openupgrade_records`` in a <= 13 fork, ``openupgrade_scripts`` from 14."""
        openupgrade = self.openupgrade_clone_dir(version)
        if self.uses_legacy_layout(version):
            return openupgrade / "odoo" / "addons" / "openupgrade_records" / "lib" / "apriori.py"
        return openupgrade / "openupgrade_scripts" / "apriori.py"

    def uses_legacy_layout(self, version: str) -> bool:
        """True where OpenUpgrade keeps migrations inside each add-on (<= 13),
        rather than under an upgrade path."""
        return odoo_major(version) <= LEGACY_LAYOUT_MAX_MAJOR

    def odoo_bin(self, version: str) -> Path:
        """The ``odoo-bin`` a step runs: the fork's own for the <= 13 layout,
        where the checkout is a full Odoo, and the Odoo clone's otherwise."""
        if self.uses_legacy_layout(version):
            return self.openupgrade_clone_dir(version) / "odoo-bin"
        return self.odoo_clone_dir(version) / "odoo-bin"

    def constraints_file(self, version: str) -> Path:
        """Build constraints for a step whose dependencies a current toolchain
        cannot build as pinned (see ``templates.render_migration_constraints``)."""
        return self.requirements_dir / f"constraints-{version}.txt"

    def validate(self) -> None:
        # migration_chain enforces source < target and the 12–19 range.
        self.chain()
