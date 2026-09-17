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
    assert env.upgrade_scripts_dir("18.0").parts[-2:] == ("openupgrade_scripts", "scripts")


def test_env_addons_path_order_custom_oca_openupgrade_core():
    env = MigrationEnv(source="13.0", target="18.0")
    entries = env.addons_path("18.0").split(",")
    assert entries[0] == str(env.addons_custom_dir("18.0"))   # operator code wins lookup
    assert entries[1] == str(env.addons_oca_dir("18.0"))
    # The OpenUpgrade checkout ROOT — so openupgrade_framework resolves too.
    assert entries[2] == str(env.openupgrade_clone_dir("18.0"))
    assert entries[3].endswith("addons")
    assert env.addons_custom_dir("18.0").parts[-3:] == ("addons", "odoo18", "custom")
    assert env.addons_oca_dir("16.0").parts[-3:] == ("addons", "odoo16", "oca")


# --- planners & templates --------------------------------------------------


def test_migration_conf_threads_addons_layout_and_openupgrade():
    env = MigrationEnv(source="13.0", target="18.0")
    conf = templates.render_migration_conf(env, "18.0")
    assert str(env.addons_custom_dir("18.0")) in conf
    assert str(env.addons_oca_dir("18.0")) in conf
    assert str(env.openupgrade_clone_dir("18.0")) in conf
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
    assert "uv venv --clear --no-project --python 3.8" in joined  # Odoo 14 → 3.8.
    # --clear: replace a half-built venv on resume; --no-project: ignore any
    # pyproject.toml at the caller's CWD (its requires-python is not Odoo's).
    assert "openupgradelib" in joined
    assert joined.count("uv venv") == 1          # only 14 (13 is docker, no venv)


def test_venvs_install_applies_the_overrides_file_and_marks_ready():
    env = MigrationEnv(source="15.0", target="16.0")
    cmds = planners.plan_migration_venvs(env)
    install = next(c.command for c in cmds if "requirements.txt" in c.command)
    assert "--overrides" in install and "overrides-16.0.txt" in install
    assert cmds[-1].command.startswith("touch")
    assert str(env.venv_ready_marker("16.0")) in cmds[-1].command


def test_venvs_skip_on_ready_marker_not_on_venv_dir():
    env = MigrationEnv(source="15.0", target="16.0")
    half_built = {env.venv_dir("16.0")}          # venv exists but installs never finished
    cmds = planners.plan_migration_venvs(env, exists=lambda p: p in half_built)
    assert any("uv venv" in c.command for c in cmds)   # rebuilt, not skipped
    done = {env.venv_ready_marker("16.0")}
    assert planners.plan_migration_venvs(env, exists=lambda p: p in done) == []


def test_overrides_lift_gevent_only_on_python_310():
    from odoo_dwg import templates
    for version in ("16.0", "17.0"):             # both run on 3.10 (gevent==21.8.0 pin, no cp310 wheel)
        text = templates.render_migration_overrides(version)
        assert "gevent==22.10.2" in text and "greenlet==2.0.2" in text
    for version in ("14.0", "15.0", "18.0"):     # 3.8 / 3.12 resolve their pins fine
        text = templates.render_migration_overrides(version)
        assert "gevent" not in text


def test_generate_migration_composes_everything():
    env = MigrationEnv(source="13.0", target="16.0")
    cmds = planners.plan_generate_migration(env)
    joined = "\n".join(c.command for c in cmds)
    assert "git clone --depth 1" in joined
    assert "uv venv" in joined
    assert "run_migration.sh" in joined


def test_requirements_dir_created_before_first_overrides_write():
    env = MigrationEnv(source="12.0", target="18.0")
    cmds = planners.plan_generate_migration(env)
    requirements_dir = str(env.requirements_dir)
    mkdir_idx = next(
        i for i, c in enumerate(cmds)
        if c.command.startswith("mkdir") and requirements_dir in c.command
    )
    overrides_idx = next(
        i for i, c in enumerate(cmds) if "overrides-" in c.command and c.command.startswith("cat >")
    )
    assert mkdir_idx < overrides_idx


def test_venvs_plan_is_self_sufficient_about_directories():
    env = MigrationEnv(source="12.0", target="14.0")
    cmds = planners.plan_migration_venvs(env)
    assert cmds[0].command.startswith("mkdir -p")
    assert str(env.requirements_dir) in cmds[0].command


def test_tree_creates_per_version_addons_dirs():
    env = MigrationEnv(source="13.0", target="15.0")
    cmds = planners.plan_migration_configs(env)
    mkdir = cmds[0].command
    assert mkdir.startswith("mkdir -p")
    for version in ("14.0", "15.0"):
        assert str(env.addons_custom_dir(version)) in mkdir
        assert str(env.addons_oca_dir(version)) in mkdir


def test_docker_provision_plans_are_pure_text():
    engine = planners.plan_docker_engine()
    assert any("docker.io" in c.command for c in engine)
    assert any("systemctl enable --now docker" in c.command for c in engine)
    pulls = planners.plan_pull_openupgrade_images()
    assert [c.command for c in pulls] == ["docker pull odoo:13.0", "docker pull odoo:12.0"]


def test_clean_migration_removes_only_the_environment_by_default():
    env = MigrationEnv(source="12.0", target="18.0")
    cmds = planners.plan_clean_migration(env.root)
    assert len(cmds) == 1
    assert cmds[0].command.startswith("rm -rf")
    assert str(env.root) in cmds[0].command
    assert ".repos" not in cmds[0].command


def test_clean_migration_includes_shared_repos_only_on_opt_in():
    env = MigrationEnv(source="12.0", target="18.0")
    cmds = planners.plan_clean_migration(env.root, env.repos_dir)
    assert len(cmds) == 2
    assert str(env.repos_dir) in cmds[1].command
    assert cmds[1].command.startswith("rm -rf")


# --- per-step interpreter overrides ---------------------------------------


def test_override_pins_one_step_and_leaves_the_rest_recommended():
    env = MigrationEnv(source="15.0", target="18.0")
    choice = env.set_interpreter_override("16.0", "3.11")
    assert (choice.python, choice.out_of_range) == ("3.11", False)
    assert env.interpreter("16.0") == ("3.11", "uv")
    # Every other step keeps the matrix recommendation.
    assert env.interpreter("17.0") == ("3.10", "uv")
    assert env.interpreter("18.0") == ("3.12", "uv")


def test_override_drives_the_venv_command_and_the_requirements_repair():
    from odoo_dwg import planners, templates

    env = MigrationEnv(source="15.0", target="17.0")
    env.set_interpreter_override("16.0", "3.11")
    joined = "\n".join(c.command for c in planners.plan_migration_venvs(env))
    assert "--python 3.11 " in joined
    # The 3.10-only gevent repair must follow the interpreter actually used:
    # present for the still-3.10 step, absent for the pinned 3.11 one.
    assert "gevent==22.10.2" in templates.render_migration_overrides("17.0", "3.10")
    assert "gevent==22.10.2" not in templates.render_migration_overrides("16.0", "3.11")


def test_out_of_range_override_is_reported_but_still_applied():
    env = MigrationEnv(source="13.0", target="15.0")
    # Odoo 14 tops out at 3.10 (derived from its Jammy bucket).
    choice = env.set_interpreter_override("14.0", "3.12")
    assert choice.out_of_range and choice.crossed.value == "3.10"
    assert env.interpreter("14.0") == ("3.12", "uv")
    env.clear_interpreter_override("14.0")
    assert env.interpreter("14.0") == ("3.8", "uv")


def test_override_refused_for_docker_steps_and_off_chain_versions():
    env = MigrationEnv(source="12.0", target="15.0")
    with pytest.raises(ValueError, match="cannot be overridden"):
        env.set_interpreter_override("13.0", "3.8")
    with pytest.raises(ValueError, match="not a step in this chain"):
        env.set_interpreter_override("18.0", "3.12")
    # A refused override leaves nothing behind.
    assert env.interpreter_overrides == {}
