"""Migration preflight — chain-scoped readiness verification (F3.1).

Two scopes, because database facts need a live database:

- *host*: the tools every chain needs (``uv`` for the per-step interpreters),
  PostgreSQL reachability and role, source-dump integrity (``pg_restore --list``,
  which also enforces the custom format), and the addons layout.
- *database*: the restored database's actual Odoo version (``ir_module_module``,
  ``base``) vs. the declared source, the installed-module list, and per-step
  addons coverage.

``gather_*`` functions do I/O via ``system`` probes; ``preflight_rows`` is pure
so the table logic is unit-tested by injecting facts — the ``provisioning``
pattern. The same implementation backs the menu action, the generate flow, and
(as rendered bash) the ``run_migration.sh`` driver.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import system
from .models import DEFAULT_DB_ROLE, MigrationEnv, odoo_major

Exists = Callable[[Path], bool]


@dataclass
class HostFacts:
    uv: bool = False
    postgres_running: bool = False
    dev_role: str = DEFAULT_DB_ROLE
    # None: it could not be told without a password prompt.
    dev_role_exists: bool | None = False
    dump_path: str | None = None
    dump_readable: bool = False
    dump_listable: bool = False
    dump_detail: str = ""
    addons_layout_present: bool = False


@dataclass
class DbFacts:
    declared_source: str
    base_version: str | None = None
    installed_modules: list[str] = field(default_factory=list)
    # ``{module: author}`` as recorded in ir_module_module. An installed module
    # with no row here is treated as having no author, which is blocking.
    module_authors: dict[str, str] = field(default_factory=dict)


@dataclass
class Coverage:
    """Per-step coverage split by what the operator can actually act on."""

    # ``{version: [module]}`` — code the step needs and nobody provides.
    blocking: dict[str, list[str]] = field(default_factory=dict)
    # ``{version: [module]}`` — Odoo's own modules, dropped upstream, which the
    # upgrade removes by itself.
    warnings: dict[str, list[str]] = field(default_factory=dict)
    # Modules resolved from the operator's own per-version custom directory.
    customs: set[str] = field(default_factory=set)
    # ``[version]`` — steps whose sources are not on disk at all. Classifying a
    # module against nothing would report every one of them as missing, `base`
    # among them, and send the operator looking for code that is not the problem.
    ungenerated: list[str] = field(default_factory=list)


def gather_host_facts(env: MigrationEnv, dump_path: str | None = None) -> HostFacts:
    """Probe the host for this chain's requirements (I/O)."""
    facts = HostFacts(
        uv=system.has_tool("uv"),
        postgres_running=system.postgres_running(env.db_port),
        dev_role=env.db_user,
        dump_path=dump_path,
        addons_layout_present=all(
            env.addons_custom_dir(v).is_dir() and env.addons_oca_dir(v).is_dir()
            for v in env.chain()
        ),
    )
    if facts.postgres_running:
        facts.dev_role_exists = system.db_role_exists(env.db_user, env.db_port)
    if dump_path:
        facts.dump_readable = Path(dump_path).is_file()
        if facts.dump_readable:
            facts.dump_listable, facts.dump_detail = system.pg_restore_lists(dump_path)
    return facts


def gather_db_facts(env: MigrationEnv, db: str) -> DbFacts:
    """Read version/module facts from an existing database (I/O via psql)."""
    base_version = system.psql_scalar(
        "SELECT latest_version FROM ir_module_module WHERE name='base'",
        db, env.db_host, env.db_port, env.db_user,
    )
    modules_raw = system.psql_scalar(
        "SELECT string_agg(name, ',' ORDER BY name) FROM ir_module_module WHERE state='installed'",
        db, env.db_host, env.db_port, env.db_user,
    )
    modules = [m for m in (modules_raw or "").split(",") if m]
    # Name and author together, so coverage can tell Odoo's own churn from code
    # the operator owes the migration. Tab-separated: an author may contain a
    # comma ("Odoo Community Association (OCA), Tecnativa").
    authors_raw = system.psql_scalar(
        "SELECT string_agg(name || E'\\t' || coalesce(author, ''), E'\\n' ORDER BY name) "
        "FROM ir_module_module WHERE state='installed'",
        db, env.db_host, env.db_port, env.db_user,
    )
    authors: dict[str, str] = {}
    for line in (authors_raw or "").splitlines():
        name, _, author = line.partition("\t")
        if name:
            authors[name] = author
    return DbFacts(declared_source=env.source, base_version=base_version or None,
                   installed_modules=modules, module_authors=authors)


# Spellings Odoo uses for itself in ``ir_module_module.author``. The test is
# EQUALITY, never a substring: OCA modules are authored "Odoo Community
# Association (OCA)", which contains "Odoo", and treating those as Odoo's own
# would wave through exactly the modules whose absence breaks a migration.
ODOO_AUTHORS: frozenset[str] = frozenset(
    {"odoo s.a.", "odoo sa", "openerp s.a.", "openerp sa", "odoo"}
)


def is_odoo_authored(author: str | None) -> bool:
    """True when a module is Odoo's own, so its disappearance is Odoo's churn
    rather than something the operator must supply."""
    return (author or "").strip().lower() in ODOO_AUTHORS


_APRIORI_CACHE: dict[str, dict[str, str]] = {}


def read_apriori(path: Path) -> dict[str, str]:
    """``{old module: new module}`` from an OpenUpgrade ``apriori.py``, merging
    ``renamed_modules`` and ``merged_modules``.

    Parsed with ``ast``, never executed: the file is literal by construction and
    there is no reason to run a checkout's code to read two dicts. A missing or
    unreadable file yields an empty mapping — the caller reports that, so it does
    not read as "nothing was renamed"."""
    key = str(path)
    if key in _APRIORI_CACHE:
        return _APRIORI_CACHE[key]
    mapping: dict[str, str] = {}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        # Not cached: the clone may appear later in the same session.
        return mapping
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if not names & {"renamed_modules", "merged_modules"}:
            continue
        try:
            value = ast.literal_eval(node.value)
        except ValueError:
            continue
        if isinstance(value, dict):
            mapping.update(
                {str(k): str(v) for k, v in value.items() if isinstance(v, str)}
            )
    _APRIORI_CACHE[key] = mapping
    return mapping


def apriori_path(env: MigrationEnv, version: str) -> Path:
    """Where a step's OpenUpgrade checkout declares its module renames/merges."""
    return env.apriori_file(version)


def coverage_sources(env: MigrationEnv, version: str) -> list[Path]:
    """The directories a step resolves modules from, custom first — the same ones
    the generated driver checks, for either OpenUpgrade layout."""
    return env.coverage_dirs(version)


def gather_coverage(
    env: MigrationEnv,
    modules: list[str],
    exists: Exists = Path.exists,
    authors: dict[str, str] | None = None,
) -> Coverage:
    """Per **native** step, work out which installed modules that step cannot
    resolve, and split them by who has to do something about it.

    A module counts as covered when it resolves directly, or when the successor
    OpenUpgrade declares for it (renamed or merged) resolves — a 12 → 19 chain is
    full of core modules Odoo renamed, and asking the operator to supply those is
    asking for the impossible. What is left is Odoo's own dropped code (a warning;
    the upgrade removes it) or somebody else's (blocking; the step needs it).

    Every step is native, so every step's coverage is verifiable."""
    coverage = Coverage()
    authors = authors or {}
    for version in env.chain():
        sources = coverage_sources(env, version)
        if not any(exists(src) for src in sources):
            # Nothing to resolve against: the environment was never generated, or
            # its clones are gone. Say that instead of blaming every module.
            coverage.ungenerated.append(version)
            continue
        renames = read_apriori(apriori_path(env, version))
        blocking: list[str] = []
        warnings: list[str] = []
        for module in modules:
            found = next((src for src in sources if exists(src / module)), None)
            if found is None:
                # One hop through what OpenUpgrade declares, then give up.
                successor = renames.get(module)
                if successor and any(exists(src / successor) for src in sources):
                    continue
                if is_odoo_authored(authors.get(module)):
                    warnings.append(module)
                else:
                    blocking.append(module)
            elif found == sources[0]:
                coverage.customs.add(module)
        if blocking:
            coverage.blocking[version] = blocking
        if warnings:
            coverage.warnings[version] = warnings
    return coverage


def _same_major(base_version: str, declared_source: str) -> bool:
    """Whether a database's ``base`` version is the declared source's major. An
    unparseable version (a non-Odoo database) is simply not a match."""
    try:
        return odoo_major(base_version) == odoo_major(declared_source)
    except ValueError:
        return False


def preflight_rows(
    host: HostFacts,
    db: DbFacts | None = None,
    coverage: Coverage | None = None,
    customs: set[str] | None = None,
    custom_dir_for: Callable[[str], Path] | None = None,
) -> list[tuple[str, str, str]]:
    """Pure: map preflight facts to (state, check, detail) rows
    (state ∈ OK/WARN/MISSING/INFO). Database rows are 'skipped', not failed, when
    no DB was given."""
    rows: list[tuple[str, str, str]] = []

    rows.append(("OK" if host.uv else "MISSING", "uv",
                 "present" if host.uv else "not installed (needed to build the native venvs)"))

    if not host.postgres_running:
        rows.append(("MISSING", "PostgreSQL", "not reachable"))
    else:
        rows.append(("OK", "PostgreSQL", "reachable"))
        if host.dev_role_exists is None:
            rows.append(("WARN", f"DB role ({host.dev_role})", "could not check without sudo — run it with sudo, or connect as the role once"))
        else:
            rows.append(("OK" if host.dev_role_exists else "MISSING",
                         f"DB role ({host.dev_role})",
                         "present" if host.dev_role_exists else "not found (see provision)"))

    if host.dump_path is None:
        rows.append(("INFO", "Source dump", "skipped (no dump given)"))
    elif not host.dump_readable:
        rows.append(("MISSING", "Source dump", f"not readable: {host.dump_path}"))
    elif not host.dump_listable:
        rows.append(("MISSING", "Source dump",
                     f"pg_restore cannot list it — a custom-format dump (pg_dump -Fc) is required. {host.dump_detail}".strip()))
    else:
        rows.append(("OK", "Source dump", host.dump_path))

    rows.append(("OK" if host.addons_layout_present else "WARN", "Addons layout",
                 "present" if host.addons_layout_present
                 else "addons/odoo<major>/{custom,oca} dirs absent — regenerate the environment"))

    if db is None:
        rows.append(("INFO", "Database checks", "skipped (no database named)"))
        return rows

    if db.base_version is None:
        rows.append(("MISSING", "Database version", "cannot read ir_module_module (is it an Odoo database?)"))
    elif _same_major(db.base_version, db.declared_source):
        rows.append(("OK", "Database version", f"base {db.base_version} matches source {db.declared_source}"))
    else:
        rows.append(("MISSING", "Database version",
                     f"base is {db.base_version} but the environment was generated for source {db.declared_source}"))

    rows.append(("OK", "Installed modules", f"{len(db.installed_modules)} installed"))

    for version in sorted(coverage.ungenerated if coverage else ()):
        rows.append(("MISSING", f"Coverage ({version})",
                     "that step's sources are not on disk — generate the environment before "
                     "reading coverage"))

    for version, missing_modules in sorted((coverage.blocking if coverage else {}).items()):
        target = str(custom_dir_for(version)) if custom_dir_for else f"addons/odoo{odoo_major(version)}/custom"
        listing = ", ".join(missing_modules[:8]) + ("…" if len(missing_modules) > 8 else "")
        rows.append(("MISSING", f"Coverage ({version})",
                     f"{listing} — place each module's {version} branch in {target}"))

    # Odoo's own modules, dropped upstream: named, but never a reason to refuse —
    # the upgrade uninstalls them and there is nothing for the operator to supply.
    for version, dropped in sorted((coverage.warnings if coverage else {}).items()):
        listing = ", ".join(dropped[:8]) + ("…" if len(dropped) > 8 else "")
        rows.append(("WARN", f"Dropped by Odoo ({version})",
                     f"{listing} — not in {version} and not renamed; OpenUpgrade removes them"))

    for module in sorted(customs or ()):
        rows.append(("WARN", f"Custom module {module}",
                     "needs per-version adapted code (and migrations/ scripts when data changes) — presence is not sufficient; see the staging workflow"))

    return rows
