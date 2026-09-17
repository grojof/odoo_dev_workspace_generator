"""Unit tests for the migration preflight — pure rows, coverage, driver bash."""

from __future__ import annotations

from odoo_dwg import preflight, templates
from odoo_dwg.models import MigrationEnv
from odoo_dwg.preflight import DbFacts, HostFacts


def _ready_host(**overrides) -> HostFacts:
    facts = HostFacts(
        uv=True,
        postgres_running=True,
        dev_role_exists=True,
        addons_layout_present=True,
    )
    for key, value in overrides.items():
        setattr(facts, key, value)
    return facts


def _states(rows: list[tuple[str, str, str]]) -> dict[str, str]:
    return {check: state for state, check, _detail in rows}


def test_native_chain_has_no_docker_rows():
    rows = preflight.preflight_rows(_ready_host())
    assert not any("Docker" in check or "Image" in check for _s, check, _d in rows)
    assert _states(rows)["uv"] == "OK"


def test_plain_sql_dump_fails_with_format_guidance():
    host = _ready_host(dump_path="/tmp/db.sql", dump_readable=True, dump_listable=False)
    _state, _check, detail = next(
        r for r in preflight.preflight_rows(host) if r[1] == "Source dump"
    )
    assert "pg_dump -Fc" in detail


def test_database_scope_skipped_not_failed_without_db():
    rows = preflight.preflight_rows(_ready_host())
    state, _check, detail = next(r for r in rows if r[1] == "Database checks")
    assert state == "INFO" and "skipped" in detail


def test_version_mismatch_is_a_failure():
    db = DbFacts(declared_source="13.0", base_version="12.0.1.3")
    states = _states(preflight.preflight_rows(_ready_host(), db))
    assert states["Database version"] == "MISSING"


def test_version_match_is_ok():
    db = DbFacts(declared_source="13.0", base_version="13.0.1.3", installed_modules=["base"])
    states = _states(preflight.preflight_rows(_ready_host(), db))
    assert states["Database version"] == "OK"


def test_coverage_missing_module_names_step_and_custom_dir():
    env = MigrationEnv(source="15.0", target="16.0")
    db = DbFacts(declared_source="15.0", base_version="15.0.1.3",
                 installed_modules=["client_sales"])
    coverage = preflight.Coverage(blocking={"16.0": ["client_sales"]})
    rows = preflight.preflight_rows(
        _ready_host(), db, coverage, {"client_sales"}, custom_dir_for=env.addons_custom_dir
    )
    state, _check, detail = next(r for r in rows if r[1] == "Coverage (16.0)")
    assert state == "MISSING"
    assert "client_sales" in detail and str(env.addons_custom_dir("16.0")) in detail


def test_custom_module_flagged_even_when_coverage_passes():
    db = DbFacts(declared_source="15.0", base_version="15.0.1.3",
                 installed_modules=["client_sales"])
    rows = preflight.preflight_rows(
        _ready_host(), db, preflight.Coverage(), {"client_sales"}
    )
    state, _check, detail = next(r for r in rows if r[1] == "Custom module client_sales")
    assert state == "WARN" and "adapted" in detail


def test_gather_coverage_classifies_by_where_found():
    env = MigrationEnv(source="15.0", target="16.0")
    core = env.odoo_clone_dir("16.0") / "addons"
    custom = env.addons_custom_dir("16.0")
    present = {core / "sale", custom / "client_sales"}
    coverage = preflight.gather_coverage(
        env, ["sale", "client_sales", "ghost_module"], exists=lambda p: p in present
    )
    # No recorded author → the operator owes that code, so it blocks.
    assert coverage.blocking == {"16.0": ["ghost_module"]}
    assert coverage.warnings == {}
    assert coverage.customs == {"client_sales"}


def test_coverage_now_verifies_the_13_step_too():
    # It used to be skipped as "not verifiable" while it ran in a container.
    env = MigrationEnv(source="12.0", target="13.0")
    coverage = preflight.gather_coverage(
        env, ["sale"], exists=lambda _p: False, authors={"sale": "Acme"}
    )
    assert coverage.blocking == {"13.0": ["sale"]}


def test_driver_preflight_host_runs_before_restore_and_db_after():
    env = MigrationEnv(source="12.0", target="14.0")
    sh = templates.render_run_migration_sh(env)
    assert sh.index("preflight_host\n") < sh.index("pg_restore --no-owner")
    assert sh.index("pg_restore --no-owner") < sh.index("  preflight_db")
    assert sh.index("  preflight_db") < sh.index("checkpoint 00_source")
    # No chain needs a container any more; uv is what every step depends on.
    assert "docker" not in sh
    assert 'command -v uv' in sh
    assert "[preflight-fail]" in sh


def test_driver_verifies_the_declared_source_version():
    env = MigrationEnv(source="14.0", target="15.0")
    sh = templates.render_run_migration_sh(env)
    assert "ir_module_module" in sh
    assert 'case "$base_ver" in 14.*)' in sh
    # Coverage failure pinpoints the custom dir to fill.
    assert str(env.addons_custom_dir("15.0")) in sh
