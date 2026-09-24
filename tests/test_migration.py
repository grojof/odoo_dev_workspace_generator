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


def test_overrides_bridge_pyldap_only_where_the_branch_pins_it():
    from odoo_dwg import templates
    # Odoo 12.0 pins pyldap==2.4.28, whose setup passes `-R` to cc — a SunOS flag
    # GCC rejects, so the venv cannot be built at all. Found by building it.
    text = templates.render_migration_overrides("12.0", "3.8")
    # Both lines are needed: `--overrides` pins versions and cannot rename a
    # package, so naming python-ldap alone leaves pyldap==2.4.28 in the
    # resolution and it fails to build exactly as before.
    assert "pyldap==3.0.0.post1" in text and "python-ldap==3.1.0" in text
    # 13.0 onwards pin python-ldap themselves; overriding would be inventing.
    for version in ("13.0", "14.0", "18.0"):
        assert "pyldap" not in templates.render_migration_overrides(version)


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
        with pytest.raises(ValueError, match="[Ii]nvalid Python version"):
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


def test_a_migration_environment_can_resolve_oca_from_its_own_version_branch():
    """`addons/odoo<major>/oca` was created empty for the operator to fill by
    hand, so whether a module is ported to a step's version — a fact the branch
    states — was answered by whoever last copied something in."""
    env = MigrationEnv(source="12.0", target="13.0", oca_repos=["server-tools"])
    env.validate()
    commands = planners.plan_migration_oca(env)
    joined = "\n".join(c.command for c in commands)

    assert "https://github.com/OCA/server-tools.git" in joined
    assert str(env.oca_clone_dir("server-tools", "13.0")) in joined
    assert f"ln -sfnT {env.oca_clone_dir('server-tools', '13.0')} " in joined
    assert str(env.oca_link_dir("server-tools", "13.0")) in joined
    # An environment naming none plans none.
    assert planners.plan_migration_oca(MigrationEnv(source="12.0", target="13.0")) == []


def test_a_repository_oca_has_not_ported_is_named_and_not_fatal():
    """A module OCA has not ported is a fact the operator needs, not a reason to
    refuse to build the environment."""
    env = MigrationEnv(source="12.0", target="13.0", oca_repos=["server-tools"])
    clone = next(c.command for c in planners.plan_migration_oca(env) if "git clone" in c.command)
    # The branch is asked for before it is cloned, and its absence is reported.
    assert clone.startswith("if git ls-remote --exit-code --heads ")
    assert clone.index("ls-remote") < clone.index("git clone")
    assert "has no 13.0 branch" in clone
    # Nothing else is masked: the clone itself is not `|| true`-ed.
    assert "|| true" not in clone
    # And no link is left pointing at a clone that is not there.
    link = next(c.command for c in planners.plan_migration_oca(env) if "ln -sfnT" in c.command)
    assert link.index("[ -d ") < link.index("ln -sfnT")


def test_an_oca_repository_name_that_could_escape_the_cache_is_refused():
    for repo in ("../evil", "a/b"):
        try:
            MigrationEnv(source="12.0", target="13.0", oca_repos=[repo]).validate()
        except ValueError as error:
            assert "OCA repository" in str(error)
        else:
            raise AssertionError(f"accepted {repo!r}")


# --- a chain that carries a client's intake ------------------------------------

def _intake_env(monkeypatch, tmp_path) -> MigrationEnv:
    from odoo_dwg import intake as it

    monkeypatch.setattr(MigrationEnv, "base_dir", str(tmp_path))
    record = it.IntakeRecord("ACME_original", "acme_reader", "client-src/acme", ("custom",),
                             it.Core("ocb", "a" * 40))
    return MigrationEnv(source="12.0", target="14.0", intake=record)


def test_with_an_intake_every_step_reads_the_clients_attachments(monkeypatch, tmp_path):
    """A step that looked in Odoo's default data_dir found none of them, and the
    migrated database could not be opened with them either."""
    env = _intake_env(monkeypatch, tmp_path)
    for version in env.chain():
        assert f"data_dir = {env.data_dir}\n" in templates.render_migration_conf(env, version)
    plain = MigrationEnv(source="12.0", target="14.0")
    assert "data_dir" not in templates.render_migration_conf(plain, "13.0")


def test_the_driver_gives_the_working_database_a_filestore_before_any_step(monkeypatch, tmp_path):
    env = _intake_env(monkeypatch, tmp_path)
    driver = templates.render_run_migration_sh(env)
    reference = env.data_dir / "filestore" / "ACME_original"
    assert f"cp -al {reference} " in driver
    # after every createdb of the working database: the source restore and a resume
    assert driver.count('createdb "$DB"\n  give_filestore\n') == 2
    plain = templates.render_run_migration_sh(MigrationEnv(source="12.0", target="14.0"))
    assert "give_filestore() { :; }" in plain and "cp -al" not in plain


def test_actions_after_generation_know_the_oca_repositories_it_linked(monkeypatch, tmp_path):
    """The menu's preflight did not, and reported every OCA module as missing."""
    from odoo_dwg.workflows.migration import linked_oca_repos

    monkeypatch.setattr(MigrationEnv, "base_dir", str(tmp_path))
    env = MigrationEnv(source="12.0", target="14.0")
    assert linked_oca_repos(env) == []
    for version, repo in (("13.0", "web"), ("14.0", "l10n-spain"), ("14.0", "web")):
        target = tmp_path / "cache" / f"{repo}-{version}"
        target.mkdir(parents=True)
        env.addons_oca_dir(version).mkdir(parents=True, exist_ok=True)
        (env.addons_oca_dir(version) / repo).symlink_to(target)
    (env.addons_oca_dir("13.0") / "not_a_link").mkdir()
    assert linked_oca_repos(env) == ["l10n-spain", "web"]


def test_a_steps_requirements_come_from_its_own_manifests_under_its_names(monkeypatch, tmp_path):
    """The first client's chain stopped at 13.0 on a library only the source's
    venv had been given."""
    from odoo_dwg import preflight
    from odoo_dwg.workflows.migration import step_python_requirements

    monkeypatch.setattr(MigrationEnv, "base_dir", str(tmp_path))
    env = MigrationEnv(source="12.0", target="14.0")
    for version, apriori in (("13.0", "{'old_mod': 'new_mod'}"), ("14.0", "{}")):
        path = preflight.apriori_path(env, version)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"renamed_modules = {apriori}\nmerged_modules = {{}}\n")
        preflight._APRIORI_CACHE.clear()
    for version, deps in (("13.0", "['unidecode', 'OpenSSL']"), ("14.0", "['cryptography<39']")):
        module = env.addons_oca_dir(version) / "new_mod"
        module.mkdir(parents=True)
        (module / "__manifest__.py").write_text(
            f"{{'name': 'x', 'external_dependencies': {{'python': {deps}}}}}")
    assert step_python_requirements(env, ["old_mod", "gone"]) == {
        "13.0": ["pyOpenSSL", "unidecode"], "14.0": ["cryptography<39"]}


def test_the_driver_checks_each_steps_libraries_in_its_own_venv_before_it(monkeypatch, tmp_path):
    env = MigrationEnv(source="12.0", target="14.0")
    driver = templates.render_run_migration_sh(env)
    assert driver.count("python_deps_step() {") == 1
    for version in env.chain():
        assert f'python_deps_step {version} {env.venv_dir(version)}/bin/python' in driver


def test_a_steps_hooks_wrap_it_and_run_before_its_checkpoint(monkeypatch, tmp_path):
    """The first client's 14.0 step stopped on deprecated accounts a migration
    script needed for a moment; what to do is a decision about that client's
    data, so it is the operator's SQL, run around the step."""
    monkeypatch.setattr(MigrationEnv, "base_dir", str(tmp_path))
    env = MigrationEnv(source="12.0", target="14.0")
    driver = templates.render_run_migration_sh(env)
    assert driver.count("step_hook() {") == 1 and f"{env.hooks_dir}/" in driver
    for version in env.chain():
        pre = driver.index(f'step_hook "{version}" pre')
        post = driver.index(f'step_hook "{version}" post')
        assert pre < driver.index(f"step {version} failed") < post
        assert post < driver.index(f'checkpoint "{version}"', post)
