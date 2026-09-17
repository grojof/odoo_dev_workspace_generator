"""Coverage classification: what OpenUpgrade already accounts for, and who owes
the code when it does not.

These exist because the original check called every installed module the
operator's, and the unit tests missed it by injecting invented module lists. The
cases below are the ones a real 12 -> 19 run produced.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_dwg import preflight
from odoo_dwg.models import MigrationEnv


@pytest.fixture(autouse=True)
def _isolated_base_dir(tmp_path, monkeypatch):
    """Keep every MigrationEnv in this module inside tmp_path.

    ``MigrationEnv.base_dir`` defaults to ``~/odoo-migrations``, so a test that
    writes to a path derived from an env would scribble on a real environment's
    clones. It did, once: an earlier version of these tests overwrote the
    OpenUpgrade checkouts' own ``apriori.py`` and broke a live migration at
    step 17. Never derive a write path from a default-constructed env.
    """
    monkeypatch.setattr(MigrationEnv, "base_dir", str(tmp_path / "migrations"))
    preflight._APRIORI_CACHE.clear()


def _write_apriori(path: Path, body: str) -> Path:
    assert "/odoo-migrations/" not in str(path) or "tmp" in str(path), (
        f"refusing to write to what looks like a real environment: {path}"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    preflight._APRIORI_CACHE.pop(str(path), None)
    return path


# --- reading apriori.py -----------------------------------------------------


def test_read_apriori_merges_renamed_and_merged(tmp_path):
    path = _write_apriori(
        tmp_path / "apriori.py",
        'renamed_modules = {"web_editor": "html_editor"}\n'
        'merged_modules = {"web_kanban_gauge": "web"}\n'
        'renamed_models = {"a.b": "c.d"}\n',
    )
    assert preflight.read_apriori(path) == {
        "web_editor": "html_editor",
        "web_kanban_gauge": "web",
    }


def test_read_apriori_tolerates_absence_and_partial_files(tmp_path):
    assert preflight.read_apriori(tmp_path / "missing.py") == {}
    path = _write_apriori(tmp_path / "only_renames.py", 'renamed_modules = {"a": "b"}\n')
    assert preflight.read_apriori(path) == {"a": "b"}


def test_read_apriori_parses_and_never_executes(tmp_path):
    marker = tmp_path / "executed.txt"
    body = (
        "import pathlib\n"
        f"pathlib.Path({str(marker)!r}).write_text('boom')\n"
        'renamed_modules = {"a": "b"}\n'
    )
    path = _write_apriori(tmp_path / "hostile.py", body)
    assert preflight.read_apriori(path) == {"a": "b"}
    assert not marker.exists(), "apriori.py must be parsed, never executed"


def test_read_apriori_caches_per_path(tmp_path, monkeypatch):
    path = _write_apriori(tmp_path / "apriori.py", 'renamed_modules = {"a": "b"}\n')
    preflight.read_apriori(path)  # warms the cache

    def explode(*_args, **_kwargs):
        raise AssertionError("cached mapping should not be re-read")

    monkeypatch.setattr(Path, "read_text", explode)
    assert preflight.read_apriori(path) == {"a": "b"}


# --- who authored it --------------------------------------------------------


def test_odoo_authorship_is_an_exact_match_never_a_substring():
    assert preflight.is_odoo_authored("Odoo S.A.")
    assert preflight.is_odoo_authored("  odoo sa  ")
    assert preflight.is_odoo_authored("OpenERP S.A.")
    # The trap this rule exists for: OCA's author *contains* "Odoo", and a
    # substring test would wave through modules whose absence breaks the chain.
    assert not preflight.is_odoo_authored("Odoo Community Association (OCA)")
    assert not preflight.is_odoo_authored("Odoo Community Association (OCA), Tecnativa")
    assert not preflight.is_odoo_authored("Acme Consulting")
    assert not preflight.is_odoo_authored("")
    assert not preflight.is_odoo_authored(None)


# --- classification ---------------------------------------------------------


def test_module_openupgrade_renamed_is_covered_by_its_successor(tmp_path):
    env = MigrationEnv(source="18.0", target="19.0")
    present = {env.odoo_clone_dir("19.0") / "addons" / "html_editor"}
    _write_apriori(
        preflight.apriori_path(env, "19.0"),
        'renamed_modules = {"web_editor": "html_editor"}\n',
    )
    coverage = preflight.gather_coverage(
        env,
        ["web_editor"],
        exists=lambda p: p in present,
        authors={"web_editor": "Odoo S.A."},
    )
    assert coverage.blocking == {} and coverage.warnings == {}


def test_module_openupgrade_merged_is_covered(tmp_path):
    env = MigrationEnv(source="16.0", target="17.0")
    present = {env.odoo_clone_dir("17.0") / "addons" / "web"}
    _write_apriori(
        preflight.apriori_path(env, "17.0"),
        'merged_modules = {"web_kanban_gauge": "web"}\n',
    )
    coverage = preflight.gather_coverage(
        env,
        ["web_kanban_gauge"],
        exists=lambda p: p in present,
        authors={"web_kanban_gauge": "Odoo S.A."},
    )
    assert coverage.blocking == {} and coverage.warnings == {}


def test_odoo_code_dropped_without_a_successor_only_warns():
    env = MigrationEnv(source="13.0", target="14.0")
    coverage = preflight.gather_coverage(
        env,
        ["web_settings_dashboard"],
        exists=lambda _p: False,
        authors={"web_settings_dashboard": "Odoo S.A."},
    )
    assert coverage.warnings == {"14.0": ["web_settings_dashboard"]}
    assert coverage.blocking == {}


def test_oca_and_vendor_code_still_blocks():
    env = MigrationEnv(source="13.0", target="14.0")
    coverage = preflight.gather_coverage(
        env,
        ["web_responsive", "client_sales"],
        exists=lambda _p: False,
        authors={
            "web_responsive": "Odoo Community Association (OCA)",
            "client_sales": "Acme Consulting",
        },
    )
    assert coverage.blocking == {"14.0": ["web_responsive", "client_sales"]}
    assert coverage.warnings == {}


def test_a_successor_that_resolves_nowhere_falls_through_to_classification():
    env = MigrationEnv(source="13.0", target="14.0")
    _write_apriori(
        preflight.apriori_path(env, "14.0"),
        'renamed_modules = {"old_vendor": "new_vendor"}\n',
    )
    coverage = preflight.gather_coverage(
        env,
        ["old_vendor"],
        exists=lambda _p: False,
        authors={"old_vendor": "Acme Consulting"},
    )
    assert coverage.blocking == {"14.0": ["old_vendor"]}


# --- reporting --------------------------------------------------------------


def test_rows_keep_the_two_classes_apart():
    from odoo_dwg.preflight import DbFacts, HostFacts

    coverage = preflight.Coverage(
        blocking={"16.0": ["client_sales"]}, warnings={"16.0": ["web_diagram"]}
    )
    db = DbFacts(
        declared_source="15.0",
        base_version="15.0.1.3",
        installed_modules=["client_sales", "web_diagram"],
    )
    host = HostFacts(needs_docker=False, uv=True, postgres_running=True,
                     dev_role_exists=True, addons_layout_present=True)
    rows = preflight.preflight_rows(host, db, coverage)
    blocking = next(r for r in rows if r[1] == "Coverage (16.0)")
    dropped = next(r for r in rows if r[1] == "Dropped by Odoo (16.0)")
    assert blocking[0] == "MISSING" and "client_sales" in blocking[2]
    assert dropped[0] == "WARN" and "web_diagram" in dropped[2]
    assert "OpenUpgrade removes them" in dropped[2]


# --- the driver must apply the same rule ------------------------------------


def test_driver_coverage_reads_apriori_at_run_time_not_at_render_time():
    from odoo_dwg import templates

    env = MigrationEnv(source="12.0", target="19.0")
    sh = templates.render_run_migration_sh(env)
    # It asks for the author, which is what the classification needs.
    assert "coalesce(author, '')" in sh
    # It points at each step's apriori.py and parses it rather than executing it.
    assert str(preflight.apriori_path(env, "19.0")) in sh
    assert "ast.literal_eval" in sh
    # The rendering is pure: no mapping content is baked in, only the path.
    assert "html_editor" not in sh
    # The same exact-match author set, so the driver cannot be laxer than the menu.
    for spelling in preflight.ODOO_AUTHORS:
        assert spelling in sh


def test_driver_fails_only_on_the_blocking_class():
    from odoo_dwg import templates

    env = MigrationEnv(source="12.0", target="19.0")
    sh = templates.render_run_migration_sh(env)
    assert "sys.exit(1 if blocking else 0)" in sh
    assert 'fail "addons coverage incomplete' in sh
    # A dropped Odoo module is reported, never fatal.
    assert "OpenUpgrade removes it" in sh
