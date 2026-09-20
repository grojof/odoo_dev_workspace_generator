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
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import system
from .i18n import tf
from .models import DEFAULT_DB_ROLE, MigrationEnv, ModuleDecision, odoo_major

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
    # ``{version: [(module, decision, reason)]}`` — a module with no successor
    # that a recorded decision accounts for. Not blocking: it was answered.
    decided: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
    # ``{version: [(module, decision, why it no longer holds)]}`` — a decision
    # the sources have overtaken. Reported, never applied.
    stale: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
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
    # ValueError covers UnicodeDecodeError: a checkout may hold anything.
    except (OSError, ValueError, SyntaxError):
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
        # TypeError: `{[1]: 'b'}` is a literal ast can build but not evaluate.
        except (ValueError, TypeError):
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


def tree_digest(root: Path) -> str | None:
    """A content digest of a module directory, or None when it is not there.

    Content and not timestamps: a ``cp -a`` and a ``git checkout`` both preserve
    times that say nothing about what the files hold. The throwaway git
    repository staging leaves inside a stage directory is skipped — it is the
    migrator's scaffolding, not the module.
    """
    if not root.is_dir():
        return None
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if ".git" in path.relative_to(root).parts:
            continue
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        if path.is_file():
            try:
                digest.update(path.read_bytes())
            except OSError:
                digest.update(b"<unreadable>")
    return digest.hexdigest()


def divergence(env: MigrationEnv, module: str, promoted, versions: list[str]) -> list[tuple[str, str]]:
    """``(version, state)`` per step: how the environment's copy of a module and
    its promoted copy relate.

    Promotion copies, so the two drift as soon as work continues in either. This
    names the drift; it does not resolve it, and neither copy is authoritative —
    the operator decides which one is right.
    """
    rows: list[tuple[str, str]] = []
    for version in versions:
        staged = tree_digest(env.addons_custom_dir(version) / module)
        kept = tree_digest(promoted.module_dir(version, module))
        if staged is None and kept is None:
            continue
        if kept is None:
            rows.append((version, "not promoted"))
        elif staged is None:
            rows.append((version, "only promoted"))
        else:
            rows.append((version, "same" if staged == kept else "diverged"))
    return rows


def coverage_sources(env: MigrationEnv, version: str) -> list[Path]:
    """The directories a step resolves modules from, custom first — the same ones
    the generated driver checks, for either OpenUpgrade layout."""
    return env.coverage_dirs(version)


def gather_coverage(
    env: MigrationEnv,
    modules: list[str],
    exists: Exists = Path.exists,
    authors: dict[str, str] | None = None,
    decisions: list[ModuleDecision] | None = None,
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
        decided: list[tuple[str, str, str]] = []
        stale: list[tuple[str, str, str]] = []
        recorded = {d.module: d for d in (decisions or [])
                    if d.source == env.source and d.target == env.target}
        for module in modules:
            found = next((src for src in sources if exists(src / module)), None)
            # One hop through what OpenUpgrade declares.
            successor = renames.get(module)
            resolved_successor = bool(
                successor and any(exists(src / successor) for src in sources)
            )
            answer = recorded.get(module)
            if answer is not None:
                # A decision is never believed over the sources. It was made about
                # a module that resolved nowhere and had no successor; if either
                # is no longer true, say what changed instead of applying it.
                overtaken = _overtaken(answer, found is not None, successor, resolved_successor)
                if overtaken:
                    stale.append((module, answer.decision, overtaken))
                elif found is None and not resolved_successor:
                    decided.append((module, answer.decision, answer.reason))
                    continue
            if found is None:
                if resolved_successor:
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
        if decided:
            coverage.decided[version] = decided
        if stale:
            coverage.stale[version] = stale
    return coverage


def _overtaken(
    answer: ModuleDecision, resolves: bool, successor: str | None, successor_resolves: bool
) -> str:
    """Why a recorded decision no longer holds, or "" when it still does."""
    if resolves:
        return tf("the module now resolves in this step's sources")
    if successor_resolves:
        return tf("OpenUpgrade now declares {} as its successor", successor)
    return ""


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
                 tf("present") if host.uv
                 else tf("not installed (needed to build the native venvs)")))

    if not host.postgres_running:
        rows.append(("MISSING", "PostgreSQL", tf("not reachable")))
    else:
        rows.append(("OK", "PostgreSQL", tf("reachable")))
        # The same name as the provision check's row: one thing, one name.
        role_label = tf("Development role ({})", host.dev_role)
        if host.dev_role_exists is None:
            rows.append(("WARN", role_label,
                         tf("could not check without sudo — run it with sudo, or connect as the "
                            "role once")))
        else:
            rows.append(("OK" if host.dev_role_exists else "MISSING", role_label,
                         tf("present") if host.dev_role_exists
                         else tf("not found (see provision)")))

    dump_label = tf("Source dump")
    if host.dump_path is None:
        rows.append(("INFO", dump_label, tf("skipped (no dump given)")))
    elif not host.dump_readable:
        rows.append(("MISSING", dump_label, tf("not readable: {}", host.dump_path)))
    elif not host.dump_listable:
        rows.append(("MISSING", dump_label,
                     tf("pg_restore cannot list it — a custom-format dump (pg_dump -Fc) is "
                        "required. {}", host.dump_detail).strip()))
    else:
        rows.append(("OK", dump_label, host.dump_path))

    rows.append(("OK" if host.addons_layout_present else "WARN", tf("Addons layout"),
                 tf("present") if host.addons_layout_present
                 else tf("addons/odoo<major>/{custom,oca} dirs absent — regenerate the "
                         "environment")))

    if db is None:
        rows.append(("INFO", tf("Database checks"), tf("skipped (no database named)")))
        return rows

    db_label = tf("Database version")
    if db.base_version is None:
        rows.append(("MISSING", db_label,
                     tf("cannot read ir_module_module (is it an Odoo database?)")))
    elif _same_major(db.base_version, db.declared_source):
        rows.append(("OK", db_label,
                     tf("base {} matches source {}", db.base_version, db.declared_source)))
    else:
        rows.append(("MISSING", db_label,
                     tf("base is {} but the environment was generated for source {}",
                        db.base_version, db.declared_source)))

    rows.append(("OK", tf("Installed modules"), tf("{} installed", len(db.installed_modules))))

    for version in sorted(coverage.ungenerated if coverage else ()):
        rows.append(("MISSING", tf("Coverage ({})", version),
                     tf("that step's sources are not on disk — generate the environment before "
                        "reading coverage")))

    for version, missing_modules in sorted((coverage.blocking if coverage else {}).items()):
        target = str(custom_dir_for(version)) if custom_dir_for else f"addons/odoo{odoo_major(version)}/custom"
        listing = ", ".join(missing_modules[:8]) + ("…" if len(missing_modules) > 8 else "")
        rows.append(("MISSING", tf("Coverage ({})", version),
                     tf("{} — place each module's {} branch in {}", listing, version, target)))

    for version, entries in sorted((coverage.decided if coverage else {}).items()):
        for module, decision, reason in entries:
            rows.append(("INFO", tf("Decided ({})", version),
                         tf("{}: {}{}", module, decision, f" — {reason}" if reason else "")))

    # A decision the sources have overtaken is reported, never applied: the
    # module is classified as if it had none, and this row says why.
    for version, entries in sorted((coverage.stale if coverage else {}).items()):
        for module, decision, why in entries:
            rows.append(("WARN", tf("Decision no longer holds ({})", version),
                         tf("{} was decided {} — {}", module, decision, why)))

    # Odoo's own modules, dropped upstream: named, but never a reason to refuse —
    # the upgrade uninstalls them and there is nothing for the operator to supply.
    for version, dropped in sorted((coverage.warnings if coverage else {}).items()):
        listing = ", ".join(dropped[:8]) + ("…" if len(dropped) > 8 else "")
        rows.append(("WARN", tf("Dropped by Odoo ({})", version),
                     tf("{} — not in {} and not renamed; OpenUpgrade removes them",
                        listing, version)))

    for module in sorted(customs or ()):
        rows.append(("WARN", tf("Custom module {}", module),
                     tf("needs per-version adapted code (and migrations/ scripts when data "
                        "changes) — presence is not sufficient; see the staging workflow")))

    return rows
