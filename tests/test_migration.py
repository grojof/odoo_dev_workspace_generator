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
    # uv floor is 3.8: 13/14/15 native on 3.8, 16/17 on 3.10, 18/19 on 3.12.
    assert migration_interpreter("13.0") == ("3.8", "uv")
    assert migration_interpreter("14.0") == ("3.8", "uv")
    assert migration_interpreter("16.0") == ("3.10", "uv")
    assert migration_interpreter("18.0") == ("3.12", "uv")


def test_every_step_of_every_chain_is_native():
    for source, target in (("12.0", "19.0"), ("13.0", "18.0"), ("12.0", "13.0")):
        env = MigrationEnv(source=source, target=target)
        assert all(migration_interpreter(v)[1] == "uv" for v in env.chain()), (source, target)


def test_env_derived_paths():
    env = MigrationEnv(source="13.0", target="18.0")
    assert env.chain() == ["14.0", "15.0", "16.0", "17.0", "18.0"]
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


def test_run_migration_sh_runs_the_13_step_natively_with_an_explicit_addons_path():
    env = MigrationEnv(source="12.0", target="14.0")  # steps 13 and 14
    sh = templates.render_run_migration_sh(env)
    assert "docker" not in sh
    # The <= 13 step runs the fork's own odoo-bin from its venv...
    assert f'{env.venv_dir("13.0")}/bin/python {env.odoo_bin("13.0")}' in sh
    # ...and neither of the >= 14 flags, which do not exist on that branch.
    step13 = sh.split("upgrade to 13.0")[1].split("upgrade to 14.0")[0]
    assert "--upgrade-path" not in step13 and "--load=" not in step13
    # The 14 step keeps them.
    assert "--load=base,web,openupgrade_framework" in sh


def test_the_13_step_config_names_the_forks_own_addons():
    # The whole point: an add-ons path that misses the fork's addons silently
    # skips every add-on migration script while the step still succeeds.
    env = MigrationEnv(source="12.0", target="14.0")
    conf = templates.render_migration_conf(env, "13.0")
    assert str(env.openupgrade_clone_dir("13.0") / "addons") in conf
    assert "odoo-13.0" not in conf  # there is no separate Odoo clone for it


def test_clones_openupgrade_always_odoo_only_for_native():
    env = MigrationEnv(source="12.0", target="14.0")  # 13 docker, 14 native
    cmds = planners.plan_migration_clones(env)
    joined = "\n".join(c.command for c in cmds)
    assert "openupgrade-13.0" in joined  # OU cloned even for the docker step
    assert "odoo-13.0" not in joined     # no Odoo clone for the docker step
    assert "openupgrade-14.0" in joined and "odoo-14.0" in joined


def test_every_step_gets_a_uv_venv():
    env = MigrationEnv(source="12.0", target="14.0")
    cmds = planners.plan_migration_venvs(env)
    joined = "\n".join(c.command for c in cmds)
    assert "uv venv --clear --no-project --python 3.8" in joined  # 13 and 14 → 3.8.
    # --clear: replace a half-built venv on resume; --no-project: ignore any
    # pyproject.toml at the caller's CWD (its requires-python is not Odoo's).
    assert "openupgradelib" in joined
    assert joined.count("uv venv") == 2          # one per step, 13 included


def test_the_13_step_installs_the_forks_requirements_with_build_constraints():
    env = MigrationEnv(source="12.0", target="14.0")
    joined = "\n".join(c.command for c in planners.plan_migration_venvs(env))
    # The fork is Odoo for that branch, so its own requirements.txt is installed.
    assert str(env.openupgrade_clone_dir("13.0") / "requirements.txt") in joined
    # vatnumber==1.2 needs a setuptools that still has use_2to3.
    assert "constraints-13.0.txt" in joined and "--build-constraints" in joined
    assert "setuptools<58" in "\n".join(c.command for c in planners.plan_migration_venvs(env))
    # A modern step needs no build constraints.
    modern = "\n".join(
        c.command for c in planners.plan_migration_venvs(MigrationEnv(source="17.0", target="18.0"))
    )
    assert "--build-constraints" not in modern


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


def test_override_refused_for_off_chain_versions():
    env = MigrationEnv(source="12.0", target="15.0")
    with pytest.raises(ValueError, match="not a step in this chain"):
        env.set_interpreter_override("18.0", "3.12")
    # A refused override leaves nothing behind.
    assert env.interpreter_overrides == {}
    # The 13 step is a step like any other now, so it can be pinned.
    assert env.set_interpreter_override("13.0", "3.9").python == "3.9"


def test_venv_plan_pins_setuptools_only_where_pkg_resources_is_imported():
    """Odoo <= 16 imports pkg_resources, which setuptools dropped in 81. Which
    setuptools a venv resolves depends on the step's interpreter, so the step
    that needs it must pin it rather than hope."""
    from odoo_dwg import planners

    env = MigrationEnv(source="12.0", target="19.0")
    installs = {
        version: next(
            c.command
            for c in planners.plan_migration_venvs(env)
            if "psycopg2-binary" in c.command and f"odoo{version.split('.')[0]}" in c.command
        )
        for version in env.chain()
    }
    for version in ("14.0", "15.0", "16.0"):
        assert "setuptools<81" in installs[version], version
    for version in ("17.0", "18.0", "19.0"):
        assert "setuptools" not in installs[version], version


def test_a_ready_venv_is_rebuilt_when_its_step_is_pinned_to_another_python():
    env = MigrationEnv(source="16.0", target="17.0")
    marker = env.venv_ready_marker("17.0")
    built_on = {env.venv_dir("17.0") / "pyvenv.cfg": "home = /x\nuv = 0.12\nversion_info = 3.10\n"}
    # Built on the recommended 3.10 and still wanted there: kept.
    same = planners.plan_migration_venvs(env, exists=lambda p: p == marker, read=built_on.get)
    assert not any("odoo17" in c.command for c in same)
    # Pinned to 3.12 now: rebuilt with it.
    env.set_interpreter_override("17.0", "3.12")
    rebuilt = planners.plan_migration_venvs(env, exists=lambda p: p == marker, read=built_on.get)
    assert any("--python 3.12" in c.command and "odoo17" in c.command for c in rebuilt)
    # Unreadable pyvenv.cfg: a ready venv is kept, as before.
    kept = planners.plan_migration_venvs(env, exists=lambda p: p == marker)
    assert not any("odoo17" in c.command for c in kept)


def test_operator_pins_must_be_plain_python_versions():
    env = MigrationEnv(source="16.0", target="17.0")
    for bad in ("3.x", "3.10; rm -rf ~", "python3", "3", ""):
        with pytest.raises(ValueError, match="invalid Python version"):
            env.set_interpreter_override("17.0", bad)


def test_gevent_repair_matches_any_310_patch_level():
    def repairs(python):
        text = templates.render_migration_overrides("17.0", python)
        return [line for line in text.splitlines() if not line.startswith("# Generated")]
    assert repairs("3.10.14") == repairs("3.10")
    assert "gevent==22.10.2" in repairs("3.10")
    assert repairs("3.12") == []


# --- the generated driver's checkpoint discipline ----------------------------


def _driver(source="15.0", target="17.0") -> str:
    return templates.render_run_migration_sh(MigrationEnv(source=source, target=target))


def test_coverage_gets_its_modules_from_the_environment_not_stdin():
    """The helper's program *is* python's stdin (a heredoc), so a piped module
    list would be lost and every module would silently pass."""
    sh = _driver()
    assert 'ODWG_MODULES_TSV="$modules_tsv" coverage_step' in sh
    assert "| coverage_step" not in sh
    assert 'modules_tsv = os.environ.get("ODWG_MODULES_TSV", "")' in sh
    assert "sys.stdin" not in sh
    # An empty list is a failure, not a pass.
    assert "no module list to check" in sh


def test_a_fresh_run_owns_the_checkpoint_directory():
    sh = _driver()
    assert 'rm -f "$CK"/*.dump "$CK"/*.dump.tmp "$CK/source.sha256"' in sh


def test_resuming_drops_everything_after_the_first_gap():
    sh = _driver()
    assert 'if [ "$gap" = 0 ] && have_ck "$step"; then' in sh
    assert 'rm -f "$CK/$step.dump"' in sh


def test_checkpoints_and_the_source_hash_are_written_atomically():
    sh = _driver()
    assert 'pg_dump -Fc "$DB" > "$CK/$1.dump.tmp"' in sh
    assert 'mv "$CK/$1.dump.tmp" "$CK/$1.dump"' in sh
    assert '"$CK/source.sha256.tmp" && mv "$CK/source.sha256.tmp" "$CK/source.sha256"' in sh
    # The hash lands before the checkpoint it describes.
    assert sh.index("source.sha256.tmp") < sh.index("checkpoint 00_source")


def test_a_checkpoint_that_cannot_be_written_stops_the_chain():
    sh = _driver()
    body = sh.split("checkpoint() {", 1)[1].split("\n}", 1)[0]
    body = "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))
    # A failing pg_dump must reach `die`, not fall through to the "[checkpoint]"
    # line and the next step, and must leave no half-written file behind.
    assert "if ! pg_dump" in body
    assert 'rm -f "$CK/$1.dump.tmp"' in body
    assert body.index("die ") < body.index('echo "[checkpoint] $1"')
    # Not `a && b || c`, which would also fire on a failing echo (shellcheck SC2015).
    assert "&&" not in body
