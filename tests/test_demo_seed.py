"""Module fates across a chain, the suggested demo set, and the seed plan.

The apriori fixtures are shaped like OpenUpgrade's own files — two literal dicts
at module level, parsed and never executed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_dwg import planners, preflight, templates
from odoo_dwg.models import MigrationEnv

APRIORI_14 = '''
renamed_modules = {
    # OCA/account-consolidation
    "account_consolidation": "account_consolidation_oca",
}
merged_modules = {
    # OCA/e-commerce
    "website_sale_product_style_badge": "website_sale",
}
'''
APRIORI_19 = '''
renamed_modules = {"mail_debrand": "mail_debranding"}
merged_modules = {"partner_contact_lang": "base"}
'''


@pytest.fixture
def chain(tmp_path):
    (tmp_path / "14.0").write_text(APRIORI_14, encoding="utf-8")
    (tmp_path / "19.0").write_text(APRIORI_19, encoding="utf-8")
    return [("14.0", tmp_path / "14.0"), ("19.0", tmp_path / "19.0")]


def test_a_rename_and_an_absorption_are_told_apart(chain):
    fates, unread = preflight.chain_fates(
        ["account_consolidation", "website_sale_product_style_badge"], chain
    )
    by_module = {fate.module: fate for fate in fates}
    assert unread == []
    renamed = by_module["account_consolidation"]
    absorbed = by_module["website_sale_product_style_badge"]
    # Both have a successor; only one of them stops existing as a module whose
    # records are its own. `read_apriori` cannot tell these apart.
    assert (renamed.kind, renamed.successor, renamed.absorbed) == (
        "renamed", "account_consolidation_oca", False
    )
    assert (absorbed.kind, absorbed.successor, absorbed.absorbed) == (
        "merged", "website_sale", True
    )
    assert renamed.version == "14.0"


def test_a_module_nothing_declares_carries_on(chain):
    fates, _ = preflight.chain_fates(["partner_firstname"], chain)
    assert (fates[0].kind, fates[0].successor) == ("carries on", "partner_firstname")
    assert fates[0].version == ""  # no step declared anything


def test_a_module_is_followed_under_the_name_a_step_gave_it(tmp_path):
    (tmp_path / "a").write_text('renamed_modules = {"old": "middle"}\nmerged_modules = {}\n')
    (tmp_path / "b").write_text('renamed_modules = {}\nmerged_modules = {"middle": "final"}\n')
    fates, _ = preflight.chain_fates(["old"], [("14.0", tmp_path / "a"), ("15.0", tmp_path / "b")])
    # The second step declares nothing about "old" — it declares it about the
    # name the first step gave it, which is the one 15.0 knows.
    assert [(f.kind, f.successor, f.version) for f in fates] == [
        ("renamed", "middle", "14.0"), ("merged", "final", "15.0")
    ]


def test_a_step_whose_sources_are_missing_is_named(tmp_path):
    (tmp_path / "14.0").write_text(APRIORI_14, encoding="utf-8")
    fates, unread = preflight.chain_fates(
        ["partner_firstname"], [("14.0", tmp_path / "14.0"), ("19.0", tmp_path / "gone")]
    )
    # Not silently treated as "19.0 declared nothing": it declared nothing that
    # could be read, and the module is not reported unchanged on its strength.
    assert unread == ["19.0"]
    assert fates[0].kind == "carries on"


def test_the_suggested_set_leads_with_the_modules_that_change(chain):
    on_disk = ["partner_firstname", "website_sale_product_style_badge", "account_consolidation"]
    suggested = preflight.suggest_demo_modules(on_disk, chain, per_kind=1)
    assert [fate.kind for fate in suggested] == ["merged", "renamed", "carries on"]


def test_nothing_is_suggested_that_is_not_on_disk(chain):
    # A module absent at the source version cannot be installed there, and the
    # rehearsal would fail for the wrong reason.
    suggested = preflight.suggest_demo_modules(["partner_firstname"], chain)
    assert [fate.module for fate in suggested] == ["partner_firstname"]


def _env(tmp_path) -> MigrationEnv:
    MigrationEnv.base_dir = str(tmp_path / "envs")
    return MigrationEnv(source="12.0", target="19.0")


def test_the_seed_prepares_the_source_version_which_the_chain_never_builds(tmp_path):
    env = _env(tmp_path)
    commands = " ".join(c.command for c in planners.plan_seed_environment(env))
    # Plain Odoo: there is no OpenUpgrade 12.0 branch, and the 12 -> 13 step runs
    # OpenUpgrade 13.
    assert "odoo-12.0" in commands and "openupgrade-12.0" not in commands
    # The source never runs a migration script.
    assert "openupgradelib" not in commands


def test_the_seed_refuses_a_module_name_a_shell_would_not_take(tmp_path):
    env = _env(tmp_path)
    with pytest.raises(ValueError):
        planners.plan_seed_demo(env, ["sale; rm -rf /"])


def test_the_seed_conf_points_at_plain_odoo_not_the_openupgrade_fork(tmp_path):
    env = _env(tmp_path)
    conf = templates.render_seed_conf(env)
    assert "odoo-12.0/addons" in conf and "openupgrade" not in conf
    assert "smtp_port = 1025" in conf  # demo data holds addresses


def test_the_seed_script_installs_one_module_at_a_time(tmp_path):
    env = _env(tmp_path)
    script = templates.render_seed_demo_sh(env, ["a_module", "b_module"])
    # One call each, so the failure names which module, not just that one failed.
    assert script.count("-i a_module ") == 1 and script.count("-i b_module ") == 1
    assert "-i a_module,b_module" not in script
    # 12.0-18.0 load demo data unless told not to; the flag's absence is the ask.
    assert "--without-demo" not in script


def test_the_seed_links_oca_for_the_source_version(tmp_path):
    MigrationEnv.base_dir = str(tmp_path / "envs")
    env = MigrationEnv(source="12.0", target="19.0", oca_repos=["e-commerce"])
    commands = " ".join(c.command for c in planners.plan_seed_environment(env))
    # The source is not a chain step, so the chain's own OCA linking skips it —
    # and a module that is not on disk at 12.0 cannot be installed at 12.0.
    assert "e-commerce" in commands and "odoo12" in commands


def test_the_chain_s_own_oca_linking_is_unchanged(tmp_path):
    MigrationEnv.base_dir = str(tmp_path / "envs")
    env = MigrationEnv(source="12.0", target="14.0", oca_repos=["e-commerce"])
    versions = {
        c.description.rsplit(" ", 1)[-1]
        for c in planners.plan_migration_oca(env)
        if c.description.startswith("Link OCA")
    }
    assert versions == {"13.0", "14.0"}  # the steps, not the source


def test_a_module_inside_a_named_oca_repository_is_on_the_path_odoo_scans(tmp_path):
    """Odoo scans an add-ons path entry exactly one level deep.

    A repository is linked as a directory of modules, so the entry has to be the
    repository, not its parent. Listing only the parent generated an environment
    that linked four OCA repositories no step could load, and coverage reported
    every one of their modules as somebody else's to supply.
    """
    MigrationEnv.base_dir = str(tmp_path / "envs")
    env = MigrationEnv(source="12.0", target="14.0", oca_repos=["e-commerce"])
    module = env.addons_oca_dir("13.0") / "e-commerce" / "website_sale_product_style_badge"
    module.mkdir(parents=True)
    (module / "__manifest__.py").write_text("{}", encoding="utf-8")
    entries = [Path(part) for part in env.addons_path("13.0").split(",")]
    # The test Odoo itself applies: some entry must be the module's own parent.
    assert module.parent in entries
    # And the source version, which a demo seed installs from.
    source_module = env.addons_oca_dir("12.0") / "e-commerce" / "some_module"
    assert source_module.parent in [Path(p) for p in env.source_addons_path.split(",")]


def test_coverage_resolves_a_module_inside_a_named_repository(tmp_path):
    MigrationEnv.base_dir = str(tmp_path / "envs")
    env = MigrationEnv(source="12.0", target="14.0", oca_repos=["partner-contact"])
    for version in env.chain():
        (env.addons_oca_dir(version) / "partner-contact" / "partner_firstname").mkdir(parents=True)
    sources = preflight.coverage_sources(env, "13.0")
    assert any((src / "partner_firstname").exists() for src in sources)


def test_the_bare_oca_directory_is_still_a_path_entry(tmp_path):
    # It predates naming repositories, and the docs still describe dropping a
    # module into it by hand.
    MigrationEnv.base_dir = str(tmp_path / "envs")
    env = MigrationEnv(source="12.0", target="14.0", oca_repos=["e-commerce"])
    assert str(env.addons_oca_dir("13.0")) in env.addons_path("13.0").split(",")


def test_the_seed_runs_the_plain_odoo_bin_not_an_openupgrade_fork(tmp_path):
    # There is no OpenUpgrade 12.0 at all — the 12 to 13 step runs OpenUpgrade 13
    # — so a source precondition naming one can never pass.
    env = _env(tmp_path)
    assert env.source_odoo_bin == env.odoo_clone_dir("12.0") / "odoo-bin"
    script = templates.render_seed_demo_sh(env, [])
    assert "openupgrade-12.0" not in script
    assert str(env.source_odoo_bin) in script
