"""The core the chain's steps from 14.0 run on: official Odoo or OCB."""

from __future__ import annotations

import pytest

from odoo_dwg import intake as it
from odoo_dwg import planners, templates
from odoo_dwg.models import MigrationEnv, chain_core_from_config
from odoo_dwg.workflows import migration as wm

COMMIT = "4" * 40


def _client_on(flavour: str | None) -> MigrationEnv:
    env = MigrationEnv(source="12.0", target="18.0")
    core = it.Core(flavour, COMMIT) if flavour else None
    env.intake = it.IntakeRecord("ACME_original", archive_root="client-src/acme", core=core)
    return env


def test_no_intake_keeps_official_odoo_and_every_path_unchanged():
    env = MigrationEnv(source="13.0", target="18.0")
    assert env.step_core == "odoo"
    assert env.odoo_clone_dir("16.0").name == "odoo-16.0"
    joined = "\n".join(c.command for c in planners.plan_migration_clones(env))
    assert "https://github.com/odoo/odoo" in joined and "OCB" not in joined


def test_a_client_on_ocb_is_migrated_on_ocb_from_14():
    env = _client_on("ocb")
    assert env.step_core == "ocb"
    commands = planners.plan_migration_clones(env)
    joined = "\n".join(c.command for c in commands)
    assert "https://github.com/OCA/OCB" in joined and "github.com/odoo/odoo" not in joined
    assert "ocb-14.0" in joined and "ocb-18.0" in joined
    assert "ocb-13.0" not in joined  # 13.0 runs OpenUpgrade's own fork
    assert any(c.description == "Clone OCB 18.0" for c in commands)
    assert str(env.odoo_clone_dir("18.0") / "addons") in env.addons_path("18.0")
    assert env.odoo_bin("18.0") == env.repos_dir / "ocb-18.0" / "odoo-bin"
    assert env.odoo_bin("13.0") == env.openupgrade_clone_dir("13.0") / "odoo-bin"


def test_the_operator_may_force_official_odoo_for_a_client_on_ocb():
    env = _client_on("ocb")
    env.chain_core = "odoo"
    assert env.odoo_clone_dir("16.0").name == "odoo-16.0"


def test_a_patched_or_unidentified_core_defaults_to_official_odoo():
    assert _client_on(None).step_core == "odoo"


def test_an_unknown_chain_core_is_refused():
    env = MigrationEnv(source="13.0", target="18.0", chain_core="enterprise")
    with pytest.raises(ValueError, match="chain core"):
        env.validate()


def test_the_choice_is_read_back_from_a_generated_step_config():
    env = _client_on("ocb")
    conf = templates.render_migration_conf(env, "16.0")
    assert chain_core_from_config(conf) == "ocb"
    env.chain_core = "odoo"
    assert chain_core_from_config(templates.render_migration_conf(env, "16.0")) == "odoo"
    assert chain_core_from_config("[options]\ndb_host = x\n") == ""


def test_later_actions_read_the_generated_core(tmp_path, monkeypatch):
    monkeypatch.setattr(MigrationEnv, "base_dir", str(tmp_path))
    generated = _client_on("ocb")
    generated.chain_core = "odoo"  # forced at generation
    conf = generated.config_file("14.0")
    conf.parent.mkdir(parents=True)
    conf.write_text(templates.render_migration_conf(generated, "14.0"))
    later = _client_on("ocb")  # a later action starts from the intake alone
    assert wm._generated_chain_core(later) == "odoo"


def test_generation_defaults_to_the_clients_core(monkeypatch):
    env = _client_on("ocb")
    seen = {}

    def choose(label, options, default_index=None):
        seen["default"] = options[default_index]
        return options[default_index]

    monkeypatch.setattr(wm, "choose", choose)
    assert wm._choose_chain_core(env) is True
    assert seen["default"] == "OCB" and env.chain_core == "ocb"


def test_a_chain_of_only_legacy_steps_asks_nothing(monkeypatch):
    env = MigrationEnv(source="12.0", target="13.0")
    monkeypatch.setattr(wm, "choose", lambda *a, **k: pytest.fail("asked"))
    assert wm._choose_chain_core(env) is True
