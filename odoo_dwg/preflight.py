"""Migration preflight — chain-scoped readiness verification (F3.1).

Two scopes, because database facts need a live database:

- *host*: tools required by the **specific** chain (``uv`` always; Docker binary,
  daemon and fallback images only when the chain includes an Odoo 12/13 step),
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

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import system
from .models import MigrationEnv, odoo_major

Exists = Callable[[Path], bool]


@dataclass
class HostFacts:
    needs_docker: bool
    docker_versions: list[str] = field(default_factory=list)
    uv: bool = False
    docker_binary: bool = False
    docker_daemon: bool = False
    docker_daemon_detail: str = ""
    images: dict[str, bool] = field(default_factory=dict)
    postgres_running: bool = False
    dev_role: str = "odoo"
    dev_role_exists: bool = False
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


def gather_host_facts(env: MigrationEnv, dump_path: str | None = None) -> HostFacts:
    """Probe the host for this chain's requirements (I/O)."""
    docker_versions = [v for v in env.chain() if not env.is_native(v)]
    facts = HostFacts(
        needs_docker=bool(docker_versions),
        docker_versions=docker_versions,
        uv=system.has_tool("uv"),
        postgres_running=system.postgres_running(),
        dev_role=env.db_user,
        dump_path=dump_path,
        addons_layout_present=all(
            env.addons_custom_dir(v).is_dir() and env.addons_oca_dir(v).is_dir()
            for v in env.chain()
        ),
    )
    if facts.postgres_running:
        facts.dev_role_exists = system.db_role_exists(env.db_user)
    if facts.needs_docker:
        facts.docker_binary = system.has_tool("docker")
        if facts.docker_binary:
            facts.docker_daemon, facts.docker_daemon_detail = system.docker_daemon_ready()
        if facts.docker_daemon:
            facts.images = {
                f"odoo:{odoo_major(v)}.0": system.docker_image_present(f"odoo:{odoo_major(v)}.0")
                for v in docker_versions
            }
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
    return DbFacts(declared_source=env.source, base_version=base_version or None,
                   installed_modules=modules)


def coverage_sources(env: MigrationEnv, version: str) -> list[Path]:
    """The directories a step's addons_path resolves modules from, custom first."""
    odoo = env.odoo_clone_dir(version)
    return [
        env.addons_custom_dir(version),
        env.addons_oca_dir(version),
        env.openupgrade_clone_dir(version),
        odoo / "addons",
        odoo / "odoo" / "addons",
    ]


def gather_coverage(
    env: MigrationEnv, modules: list[str], exists: Exists = Path.exists
) -> tuple[dict[str, list[str]], set[str]]:
    """Per **native** step: installed modules found in none of that step's addons
    sources; plus the set of modules classified *custom* (resolved from the custom
    dir, or found nowhere). Docker steps (12/13) are skipped — the official image
    provides core, and their coverage is reported as not verifiable."""
    missing: dict[str, list[str]] = {}
    customs: set[str] = set()
    for version in env.chain():
        if not env.is_native(version):
            continue
        sources = coverage_sources(env, version)
        step_missing: list[str] = []
        for module in modules:
            found = next((src for src in sources if exists(src / module)), None)
            if found is None:
                step_missing.append(module)
                customs.add(module)
            elif found == sources[0]:
                customs.add(module)
        if step_missing:
            missing[version] = step_missing
    return missing, customs


def preflight_rows(
    host: HostFacts,
    db: DbFacts | None = None,
    coverage: dict[str, list[str]] | None = None,
    customs: set[str] | None = None,
    custom_dir_for: Callable[[str], Path] | None = None,
) -> list[tuple[str, str, str]]:
    """Pure: map preflight facts to (state, check, detail) rows
    (state ∈ OK/WARN/MISSING/INFO). Docker rows appear only for chains that
    need them; database rows are 'skipped', not failed, when no DB was given."""
    rows: list[tuple[str, str, str]] = []

    rows.append(("OK" if host.uv else "MISSING", "uv",
                 "present" if host.uv else "not installed (needed to build the native venvs)"))

    if host.needs_docker:
        if not host.docker_binary:
            majors = "/".join(str(odoo_major(v)) for v in host.docker_versions)
            rows.append(("MISSING", "Docker binary", f"not installed (chain runs Odoo {majors})"))
        else:
            rows.append(("OK", "Docker binary", "present"))
            if host.docker_daemon:
                rows.append(("OK", "Docker daemon", host.docker_daemon_detail or "responding"))
                for tag, present in host.images.items():
                    rows.append(("OK" if present else "MISSING", f"Image {tag}",
                                 "present" if present else f"not pulled (docker pull {tag})"))
            else:
                rows.append(("MISSING", "Docker daemon",
                             host.docker_daemon_detail or "not responding (service down or missing docker-group permission)"))

    if not host.postgres_running:
        rows.append(("MISSING", "PostgreSQL", "not reachable"))
    else:
        rows.append(("OK", "PostgreSQL", "reachable"))
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
    elif odoo_major(db.base_version) == odoo_major(db.declared_source):
        rows.append(("OK", "Database version", f"base {db.base_version} matches source {db.declared_source}"))
    else:
        rows.append(("MISSING", "Database version",
                     f"base is {db.base_version} but the environment was generated for source {db.declared_source}"))

    rows.append(("OK", "Installed modules", f"{len(db.installed_modules)} installed"))

    for version, missing_modules in sorted((coverage or {}).items()):
        target = str(custom_dir_for(version)) if custom_dir_for else f"addons/odoo{odoo_major(version)}/custom"
        listing = ", ".join(missing_modules[:8]) + ("…" if len(missing_modules) > 8 else "")
        rows.append(("MISSING", f"Coverage ({version})",
                     f"{listing} — place each module's {version} branch in {target}"))

    for module in sorted(customs or ()):
        rows.append(("WARN", f"Custom module {module}",
                     "needs per-version adapted code (and migrations/ scripts when data changes) — presence is not sufficient; see the staging workflow"))

    return rows
