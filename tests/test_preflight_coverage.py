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


def _only_the_source_dirs(env: MigrationEnv):
    """A generated environment with empty source directories: the dirs are there,
    no module resolves in them. Coverage can then classify, instead of reporting
    the step as never generated."""
    dirs = {d for version in env.chain() for d in preflight.coverage_sources(env, version)}
    return lambda p: p in dirs


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
    present = {env.odoo_clone_dir("19.0") / "addons" / "html_editor",
               *preflight.coverage_sources(env, "19.0")}
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
    present = {env.odoo_clone_dir("17.0") / "addons" / "web",
               *preflight.coverage_sources(env, "17.0")}
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
        exists=_only_the_source_dirs(env),
        authors={"web_settings_dashboard": "Odoo S.A."},
    )
    assert coverage.warnings == {"14.0": ["web_settings_dashboard"]}
    assert coverage.blocking == {}


def test_oca_and_vendor_code_still_blocks():
    env = MigrationEnv(source="13.0", target="14.0")
    coverage = preflight.gather_coverage(
        env,
        ["web_responsive", "client_sales"],
        exists=_only_the_source_dirs(env),
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
        exists=_only_the_source_dirs(env),
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
    host = HostFacts(uv=True, postgres_running=True,
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


# --- the <= 13 layout: the fork is Odoo, with its own core add-ons ------------

from odoo_dwg import templates as _templates  # noqa: E402
from odoo_dwg.models import MigrationEnv as _Env  # noqa: E402


def test_legacy_step_resolves_from_the_fork_not_from_an_odoo_clone():
    env = _Env(source="12.0", target="14.0")
    fork = env.openupgrade_clone_dir("13.0")
    dirs = preflight.coverage_sources(env, "13.0")
    assert fork / "addons" in dirs  # web, sale, … in the fork
    assert fork / "odoo" / "addons" in dirs  # base, which odoo-bin adds itself
    assert not any(str(env.odoo_clone_dir("13.0")) in str(d) for d in dirs)  # never cloned
    assert preflight.apriori_path(env, "13.0") == (
        fork / "odoo" / "addons" / "openupgrade_records" / "lib" / "apriori.py")


def test_upgrade_path_step_keeps_its_layout():
    env = _Env(source="13.0", target="14.0")
    odoo = env.odoo_clone_dir("14.0")
    dirs = preflight.coverage_sources(env, "14.0")
    assert odoo / "addons" in dirs and odoo / "odoo" / "addons" in dirs
    assert preflight.apriori_path(env, "14.0").parts[-2:] == ("openupgrade_scripts", "apriori.py")


def test_the_driver_checks_coverage_from_the_same_places():
    env = _Env(source="12.0", target="14.0")
    sh = _templates.render_run_migration_sh(env)
    for version in env.chain():
        for directory in preflight.coverage_sources(env, version):
            assert str(directory) in sh
        assert str(preflight.apriori_path(env, version)) in sh


def test_a_missing_apriori_is_not_remembered(tmp_path):
    path = tmp_path / "apriori.py"
    assert preflight.read_apriori(path) == {}
    path.write_text("renamed_modules = {'old': 'new'}\nmerged_modules = {}\n")
    assert preflight.read_apriori(path) == {"old": "new"}


# --- decisions about modules with no successor --------------------------------


def _decided(tmp_path, monkeypatch, modules, also_on_disk=()):
    """Coverage for a 12 → 13 chain with one recorded decision, against sources
    the caller controls."""
    from odoo_dwg.models import MigrationEnv, ModuleDecision

    monkeypatch.setattr(MigrationEnv, "base_dir", str(tmp_path))
    env = MigrationEnv(source="12.0", target="13.0")
    sources = env.coverage_dirs("13.0")[0]
    sources.mkdir(parents=True, exist_ok=True)
    for name in also_on_disk:
        (sources / name).mkdir(exist_ok=True)
    decision = ModuleDecision(
        module="gone", source="12.0", target="13.0",
        decision="dropped", reason="the client does not use it",
    )
    return preflight.gather_coverage(env, modules, authors={}, decisions=[decision])


def test_a_decision_answers_a_module_with_no_successor(tmp_path, monkeypatch):
    """The same answer serves the next client: a module dropped with no successor
    between two versions is dropped for everyone migrating between them."""
    coverage = _decided(tmp_path, monkeypatch, ["gone"])
    assert coverage.decided == {"13.0": [("gone", "dropped", "the client does not use it")]}
    assert coverage.blocking == {} and coverage.stale == {}


def test_a_decision_the_sources_have_overtaken_is_reported_not_applied(tmp_path, monkeypatch):
    """A decision is never believed over the sources — an OCA module recorded as
    dead that has since been ported would otherwise keep a client on a
    workaround they no longer need."""
    coverage = _decided(tmp_path, monkeypatch, ["gone"], also_on_disk=["gone"])
    assert coverage.decided == {}
    module, decision, why = coverage.stale["13.0"][0]
    assert (module, decision) == ("gone", "dropped")
    assert "now resolves" in why


def test_a_module_with_no_decision_is_still_reported(tmp_path, monkeypatch):
    coverage = _decided(tmp_path, monkeypatch, ["other"])
    assert coverage.blocking == {"13.0": ["other"]}
    assert coverage.decided == {} and coverage.stale == {}


def test_a_hand_edited_decisions_file_cannot_stop_a_preflight():
    """It is the operator's record, carried between clients and edited by hand."""
    from odoo_dwg.models import ModuleDecision, decisions_from_json, decisions_to_json

    assert decisions_from_json("not json at all") == []
    assert decisions_from_json('{"decisions": [{"module": 1}]}') == []
    assert decisions_from_json('{"decisions": "nope"}') == []
    one = ModuleDecision(module="m", source="12.0", target="18.0", decision="dropped",
                         reason="why", evidence={"resolved": False})
    assert decisions_from_json(decisions_to_json([one])) == [one]


def test_a_module_absorbed_mid_chain_is_not_missing_at_every_later_step(tmp_path):
    """The case a real 12 -> 14 demo run produced, and stopped on.

    `account_coa_menu` is merged into `account_menu` at 13.0. At 14.0 apriori
    says nothing about the old name — it no longer exists to say anything about —
    so looking the original up at every step reported it missing for 14.0 and
    blocked the run, telling the operator to supply code that should not exist.
    """
    env = MigrationEnv(source="12.0", target="14.0")
    for version, mapping in (("13.0", '{"account_coa_menu": "account_menu"}'), ("14.0", "{}")):
        path = preflight.apriori_path(env, version)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"renamed_modules = {{}}\nmerged_modules = {mapping}\n", encoding="utf-8")
    # The successor is on disk for both steps; the original is on disk for neither.
    for version in env.chain():
        (env.addons_oca_dir(version) / "account_menu").mkdir(parents=True)

    coverage = preflight.gather_coverage(env, ["account_coa_menu"])
    assert coverage.blocking == {}
    assert coverage.warnings == {}


def test_a_module_that_really_is_missing_is_still_blocking(tmp_path):
    env = MigrationEnv(source="12.0", target="14.0")
    for version in env.chain():
        path = preflight.apriori_path(env, version)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("renamed_modules = {}\nmerged_modules = {}\n", encoding="utf-8")
        env.addons_oca_dir(version).mkdir(parents=True, exist_ok=True)
    coverage = preflight.gather_coverage(env, ["client_only_module"])
    # Carrying successors forward must not make everything resolve.
    assert coverage.blocking["13.0"] == ["client_only_module"]


def test_a_decision_follows_the_module_through_a_rename(tmp_path):
    """The operator decides about a module; the chain renames it two steps later.

    It is the same module, so the decision still answers for it — under whichever
    name they recorded, the one they started with or the one a step reported.
    """
    from odoo_dwg.models import ModuleDecision

    env = MigrationEnv(source="12.0", target="14.0")
    for version, mapping in (("13.0", '{"client_mod": "client_mod_oca"}'), ("14.0", "{}")):
        path = preflight.apriori_path(env, version)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"renamed_modules = {mapping}\nmerged_modules = {{}}\n", encoding="utf-8")
        env.addons_oca_dir(version).mkdir(parents=True, exist_ok=True)

    for recorded_as in ("client_mod", "client_mod_oca"):
        decision = ModuleDecision(module=recorded_as, source="12.0", target="14.0",
                                  decision="dropped", reason="OCA never ported it")
        coverage = preflight.gather_coverage(env, ["client_mod"], decisions=[decision])
        assert coverage.blocking == {}, f"blocked when recorded as {recorded_as}"
        # Named, not applied silently.
        assert any("dropped" in str(row) for rows in coverage.decided.values() for row in rows)


def test_a_resolvable_module_with_an_unresolvable_dependency_is_reported(tmp_path):
    """A real 12 -> 19 run failed at step 16 on this, fifteen minutes in.

    `account_statement_import_base` resolved — the OCA repository was cloned —
    but its manifest names `account_statement_base`, which lives in a *different*
    OCA repository nobody had cloned. Odoo refuses to upgrade such a module, so
    coverage saying "everything resolves" was not the same as the step running.
    """
    env = MigrationEnv(source="12.0", target="14.0")
    for version in env.chain():
        path = preflight.apriori_path(env, version)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("renamed_modules = {}\nmerged_modules = {}\n", encoding="utf-8")
        module = env.addons_oca_dir(version) / "client_mod"
        module.mkdir(parents=True)
        (module / "__manifest__.py").write_text(
            "{'name': 'x', 'depends': ['base', 'not_cloned_anywhere']}", encoding="utf-8"
        )
        (env.addons_oca_dir(version) / "base").mkdir()

    coverage = preflight.gather_coverage(env, ["client_mod"])
    assert coverage.blocking == {}          # it resolves
    assert coverage.unmet["13.0"] == {"client_mod": ["not_cloned_anywhere"]}


def test_a_manifest_that_cannot_be_read_names_no_dependency(tmp_path):
    env = MigrationEnv(source="12.0", target="14.0")
    version = "13.0"
    module = env.addons_oca_dir(version) / "broken"
    module.mkdir(parents=True)
    (module / "__manifest__.py").write_text("{not python", encoding="utf-8")
    assert preflight.missing_dependencies(
        ["broken"], [env.addons_oca_dir(version)]
    ) == {}
