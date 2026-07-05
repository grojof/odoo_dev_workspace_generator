"""Unit tests for the migration model — chain, interpreter matrix, MigrationEnv."""

from __future__ import annotations

import pytest

from odoo_dwg import planners, templates
from odoo_dwg.models import MigrationEnv, migration_chain, migration_interpreter


def test_chain_is_sequential_no_skips():
    assert migration_chain("13.0", "18.0") == ["14.0", "15.0", "16.0", "17.0", "18.0"]
    assert migration_chain("17.0", "19.0") == ["18.0", "19.0"]


def test_chain_rejects_bad_range():
    with pytest.raises(ValueError):
        migration_chain("18.0", "18.0")  # source not older than target
    with pytest.raises(ValueError):
        migration_chain("19.0", "18.0")  # source newer
    with pytest.raises(ValueError):
        migration_chain("11.0", "18.0")  # below supported range


def test_interpreter_matrix_matches_wsl_measurements():
    # uv floor is 3.8: 14/15 native on 3.8, 16/17 on 3.10, 18/19 on 3.12.
    assert migration_interpreter("14.0") == ("3.8", "uv")
    assert migration_interpreter("16.0") == ("3.10", "uv")
    assert migration_interpreter("18.0") == ("3.12", "uv")
    # 12/13 (Python 3.5/3.6) are not uv-installable → Docker.
    assert migration_interpreter("13.0") == (None, "docker")
    assert migration_interpreter("12.0") == (None, "docker")


def test_env_needs_docker_only_when_running_odoo_13():
    # 12 → 18 runs the 12→13 step (Odoo 13, Py3.6) → Docker needed.
    assert MigrationEnv(source="12.0", target="18.0").needs_docker() is True
    # 13 → 18 runs 14..18, all native → no Docker.
    assert MigrationEnv(source="13.0", target="18.0").needs_docker() is False


def test_env_derived_paths():
    env = MigrationEnv(source="13.0", target="18.0")
    assert env.chain() == ["14.0", "15.0", "16.0", "17.0", "18.0"]
    assert env.is_native("14.0") is True
    assert env.odoo_clone_dir("16.0").name == "odoo-16.0"
    assert env.openupgrade_clone_dir("16.0").name == "openupgrade-16.0"
    assert env.venv_dir("14.0").name == "odoo14"
    # addons_path threads the OpenUpgrade scripts alongside Odoo add-ons.
    assert "openupgrade_scripts" in env.addons_path("18.0")
    assert env.upgrade_scripts_dir("18.0").parts[-2:] == ("openupgrade_scripts", "scripts")


# --- planners & templates --------------------------------------------------


def test_migration_conf_includes_upgrade_scripts():
    env = MigrationEnv(source="13.0", target="18.0")
    conf = templates.render_migration_conf(env, "18.0")
    assert "openupgrade_scripts" in conf
    assert "db_host = 127.0.0.1" in conf


def test_run_migration_sh_native_step_and_checkpoints():
    env = MigrationEnv(source="13.0", target="15.0")  # steps 14, 15 (both native)
    sh = templates.render_run_migration_sh(env)
    assert "pg_restore" in sh and "checkpoint 00_source" in sh
    assert "--load=base,web,openupgrade_framework" in sh  # >= 14 command shape
    assert 'checkpoint "14.0"' in sh and 'checkpoint "15.0"' in sh
    assert 'have_ck "14.0"' in sh  # resume/skip guard


def test_run_migration_sh_uses_docker_for_odoo13_step():
    env = MigrationEnv(source="12.0", target="14.0")  # steps 13 (docker), 14 (native)
    sh = templates.render_run_migration_sh(env)
    assert "docker run --rm --network=host" in sh
    assert "odoo:13.0" in sh
    assert "(docker)" in sh and "(native)" in sh


def test_clones_openupgrade_always_odoo_only_for_native():
    env = MigrationEnv(source="12.0", target="14.0")  # 13 docker, 14 native
    cmds = planners.plan_migration_clones(env)
    joined = "\n".join(c.command for c in cmds)
    assert "openupgrade-13.0" in joined  # OU cloned even for the docker step
    assert "odoo-13.0" not in joined     # no Odoo clone for the docker step
    assert "openupgrade-14.0" in joined and "odoo-14.0" in joined


def test_venvs_only_for_native_versions_with_uv():
    env = MigrationEnv(source="12.0", target="14.0")
    cmds = planners.plan_migration_venvs(env)
    joined = "\n".join(c.command for c in cmds)
    assert "uv venv --python 3.8" in joined      # Odoo 14 → 3.8
    assert "openupgradelib" in joined
    assert joined.count("uv venv") == 1          # only 14 (13 is docker, no venv)


def test_generate_migration_composes_everything():
    env = MigrationEnv(source="13.0", target="16.0")
    cmds = planners.plan_generate_migration(env)
    joined = "\n".join(c.command for c in cmds)
    assert "git clone --depth 1" in joined
    assert "uv venv" in joined
    assert "run_migration.sh" in joined
