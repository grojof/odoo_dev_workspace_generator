"""Unit tests for pure text builders — assert on rendered content only."""

from __future__ import annotations

import json

from odoo_dwg import templates
from odoo_dwg.models import MigrationEnv, WorkspaceConfig


def test_odoo_conf_has_composed_addons_path_and_derived_port():
    cfg = WorkspaceConfig(name="acme", versions=["17.0", "18.0", "19.0"], oca_repos=["web"])
    cfg.normalize_defaults()
    conf = templates.render_odoo_conf(cfg, "18.0")
    assert f"addons_path = {cfg.addons_path('18.0')}" in conf
    assert "http_port = 8079" in conf  # 17=8069, 18=8079, 19=8089
    assert "gevent_port = 9079" in conf  # bus port = http + 1000, Odoo >= 16 key
    assert "workers = 0" in conf  # development posture
    # The shared development role, not one named after the workspace.
    assert "db_user = odoo\n" in conf


def test_odoo_conf_uses_longpolling_key_below_16():
    cfg = WorkspaceConfig(name="legacy", versions=["15.0"])
    cfg.normalize_defaults()
    conf = templates.render_odoo_conf(cfg, "15.0")
    assert "longpolling_port =" in conf
    assert "gevent_port =" not in conf


def test_readme_lists_versions_and_run_commands():
    cfg = WorkspaceConfig(name="acme", versions=["17.0", "18.0"])
    cfg.normalize_defaults()
    readme = templates.render_workspace_readme(cfg)
    assert "odoo17acme" in readme and "odoo18acme" in readme
    assert "bash scripts/setup_venv.sh" in readme
    assert "config/odoo17.conf" in readme and "config/odoo18.conf" in readme


def test_vscode_files_are_valid_json():
    cfg = WorkspaceConfig(name="acme", versions=["18.0"])
    cfg.normalize_defaults()
    for rendered in (
        templates.render_vscode_settings(cfg),
        templates.render_vscode_extensions(),
        templates.render_vscode_tasks(cfg),
        templates.render_vscode_launch(cfg),
        templates.render_code_workspace(cfg),
    ):
        json.loads(rendered)  # raises if not valid JSON


def test_launch_has_serve_shell_upgrade_and_test_per_version():
    cfg = WorkspaceConfig(name="acme", versions=["17.0", "18.0"])
    cfg.normalize_defaults()
    launch = json.loads(templates.render_vscode_launch(cfg))
    names = [c["name"] for c in launch["configurations"]]
    assert names == [
        "Odoo 17.0 (odoo17acme)",
        "Odoo 17.0 shell (odoo17acme)",
        "Odoo 17.0 upgrade modules (odoo17acme)",
        "Odoo 17.0 test module (odoo17acme)",
        "Odoo 18.0 (odoo18acme)",
        "Odoo 18.0 shell (odoo18acme)",
        "Odoo 18.0 upgrade modules (odoo18acme)",
        "Odoo 18.0 test module (odoo18acme)",
    ]
    for configuration in launch["configurations"]:
        assert configuration["type"] == "debugpy"
        assert configuration["console"] == "integratedTerminal"  # the shell needs a terminal
        assert configuration["python"].endswith(("/.venv/odoo17/bin/python", "/.venv/odoo18/bin/python"))


def test_launch_arguments_and_inputs():
    cfg = WorkspaceConfig(name="acme", versions=["18.0"])
    cfg.normalize_defaults()
    launch = json.loads(templates.render_vscode_launch(cfg))
    serve, shell, upgrade, test = (c["args"] for c in launch["configurations"])
    conf = str(cfg.config_file("18.0"))
    assert serve == ["-c", conf]
    assert shell == ["shell", "-c", conf, "-d", "${input:odooDatabase}"]
    assert upgrade == ["-c", conf, "-d", "${input:odooDatabase}", "-u", "${input:odooModules}"]
    assert test == [
        "-c", conf, "-d", "${input:odooDatabase}", "-u", "${input:odooTestModule}",
        "--test-enable", "--test-tags", "/${input:odooTestModule}", "--stop-after-init",
    ]
    inputs = {i["id"]: i for i in launch["inputs"]}
    assert set(inputs) == {"odooDatabase", "odooModules", "odooTestModule"}
    assert inputs["odooDatabase"]["default"] == "acme"
    assert all(i["type"] == "promptString" for i in inputs.values())


def test_setup_venv_script_uses_the_same_interpreter_as_the_plan():
    """An out-of-range version is built with uv in the plan, so the generated
    script must rebuild it the same way — otherwise re-running the script would
    silently replace that venv with the host python3."""
    from odoo_dwg.models import resolve_interpreter

    cfg = WorkspaceConfig(name="acme", versions=["14.0", "18.0"])
    cfg.normalize_defaults()
    interpreters = {
        version: resolve_interpreter(version, host_python="3.12") for version in cfg.versions
    }
    script = templates.render_setup_venv_sh(cfg, interpreters)
    assert "uv venv --seed --no-project --python 3.8 /" in script
    # Only the in-range version falls back to the host interpreter.
    assert script.count("python3 -m venv") == 1
    assert "odoo18" in script.split("python3 -m venv")[1]
    # The reason is stated in the script itself.
    assert "Odoo 14.0 supports Python 3.7" in script


def test_setup_venv_script_without_interpreters_keeps_the_host_python():
    cfg = WorkspaceConfig(name="acme", versions=["18.0"])
    cfg.normalize_defaults()
    script = templates.render_setup_venv_sh(cfg)
    assert "python3 -m venv" in script and "uv venv" not in script


def test_setup_venv_script_pins_setuptools_like_the_plan():
    # Re-running the script must not undo the pin the generation plan applied.
    cfg = WorkspaceConfig(name="acme", versions=["13.0", "15.0", "18.0"])
    cfg.normalize_defaults()
    script = templates.render_setup_venv_sh(cfg)
    assert "/.venv/odoo13/bin/pip install --upgrade pip wheel 'setuptools<58'" in script
    assert "/.venv/odoo15/bin/pip install --upgrade pip wheel 'setuptools<81'" in script
    assert "/.venv/odoo18/bin/pip install --upgrade pip wheel setuptools" in script


def test_setup_venv_script_applies_the_same_requirement_substitute():
    cfg = WorkspaceConfig(name="acme", versions=["12.0", "18.0"])
    cfg.normalize_defaults()
    script = templates.render_setup_venv_sh(cfg)
    assert script.count("grep -v -i -E '^pyldap") == 1
    assert "install -r /dev/stdin python-ldap==3.1.0" in script


def test_readme_states_what_each_venv_installs():
    from odoo_dwg.models import resolve_interpreter

    cfg = WorkspaceConfig(name="acme", versions=["12.0", "15.0", "18.0"])
    cfg.normalize_defaults()
    choices = {v: resolve_interpreter(v, host_python="3.12") for v in cfg.versions}
    readme = templates.render_workspace_readme(cfg, choices)
    assert "| 12.0 | 3.8 (`uv`) | `setuptools<58` | `python-ldap==3.1.0` instead of `pyldap` |" in readme
    assert "| 15.0 | 3.12 (host) | `setuptools<81` | — |" in readme
    assert "| 18.0 | 3.12 (host) | `setuptools` | — |" in readme



def test_generated_scripts_quote_paths_so_they_can_never_run(monkeypatch):
    """Validation refuses unsafe names, and the scripts still quote every path:
    a base directory with shell syntax stays inert text."""
    import shlex as _shlex

    monkeypatch.setattr(WorkspaceConfig, "base_dir", "/tmp/ws $(touch pwned)")
    cfg = WorkspaceConfig(name="acme", versions=["14.0", "18.0"])
    cfg.normalize_defaults()
    from odoo_dwg.models import resolve_interpreter
    choices = {v: resolve_interpreter(v, host_python="3.12") for v in cfg.versions}
    checked = 0
    for script in (templates.render_setup_venv_sh(cfg, choices), templates.render_run_sh(cfg, "18.0")):
        for line in script.splitlines():
            if "$(touch pwned)" in line:
                checked += 1
                # Every occurrence sits inside single quotes, where bash expands nothing.
                words = _shlex.split(line, comments=True)
                assert any("$(touch pwned)" in word for word in words), line
                assert '"' + "/tmp/ws $(touch pwned)" not in line, line
    # Without this the whole test passes vacuously the day a renderer stops
    # writing the path at all, which is exactly how it would stop guarding.
    assert checked, "the path never appeared — this test asserted nothing"


def test_the_generated_config_never_asks_odoo_to_reload_itself():
    """`reload` re-executes the process on a file change, detaching the debugger
    every launch configuration attaches (docs/editor-integration.md)."""
    cfg = WorkspaceConfig(name="acme", versions=["18.0"])
    conf = templates.render_odoo_conf(cfg, "18.0")
    assert "dev_mode = qweb,xml" in conf
    assert "reload" not in conf
    # Development posture: loopback only, threaded so a debugger can attach.
    assert "http_interface = 127.0.0.1" in conf
    assert "workers = 0" in conf
    assert "max_cron_threads = 1" in conf


def test_the_driver_keeps_its_checkpoints_and_logs_to_itself():
    """A checkpoint is a `pg_dump` of a restored copy of production, and the log
    is Odoo's log for it. Removing either line left the suite and both offline
    verifiers green."""
    script = templates.render_run_migration_sh(MigrationEnv(source="16.0", target="18.0"))
    header = script.split("fail()", 1)[0]
    assert header.index("umask 077") < header.index('mkdir -p "$CK" "$LOGS"')
    assert 'chmod 700 "$CK" "$LOGS"' in header
    # Without `-e` an unchecked restore inside a function would run on. Asserted
    # on the header rather than on a line number, which a correct edit moves.
    assert "set -euo pipefail" in header


def test_the_generated_setup_script_writes_each_ready_marker_last():
    """Neither `uv venv --seed` nor `python3 -m venv` clears the marker, so a run
    that dies mid-build would leave a half-built venv wearing the mark that tells
    every later flow to skip it."""
    cfg = WorkspaceConfig(name="acme", versions=["18.0"])
    cfg.normalize_defaults()
    script = templates.render_setup_venv_sh(cfg)
    marker = str(cfg.venv_ready_marker("18.0"))
    assert (script.index(f"rm -f {marker}")
            < script.index("pip install -r")
            < script.index(f"touch {marker}"))


def test_the_driver_records_every_step_as_it_happens():
    """The step log is what a live view follows and a cumulative report reads.
    Appended and never rewritten, so a run killed mid-step still leaves a record,
    and timestamped in the form `journalctl --since/--until` takes — a step's
    window is handed to the firewall's journal instead of guessed at."""
    script = templates.render_run_migration_sh(MigrationEnv(source="16.0", target="18.0"))

    assert 'STEPS="$LOGS/steps.tsv"' in script
    assert ">> \"$STEPS\"" in script          # appended, never truncated
    assert "$(date -Is)" in script            # what journalctl takes
    for event in ('mark - run-start', 'mark "17.0" start', 'mark "17.0" ok',
                  'mark "17.0" skip', 'mark "17.0" fail "$code"', "mark - run-ok"):
        assert event in script, event
    # `|| code=$?`, not `if ! cmd`: inside the negation `$?` is the status of not
    # having failed, so every failure was recorded as exit 0.
    assert "|| code=$?" in script
    assert 'if ! ' + templates._native_step_command(
        MigrationEnv(source="16.0", target="18.0"), "17.0"
    ) not in script
    # The step's own outcome is marked before the run gives up on it.
    assert script.index('mark "18.0" fail') < script.index("step 18.0 failed")
