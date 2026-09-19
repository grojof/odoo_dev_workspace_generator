"""Unit tests for pure text builders — assert on rendered content only."""

from __future__ import annotations

import json

from odoo_dwg import templates
from odoo_dwg.models import WorkspaceConfig


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
    for script in (templates.render_setup_venv_sh(cfg, choices), templates.render_run_sh(cfg, "18.0")):
        for line in script.splitlines():
            if "$(touch pwned)" in line:
                # Every occurrence sits inside single quotes, where bash expands nothing.
                words = _shlex.split(line, comments=True)
                assert any("$(touch pwned)" in word for word in words), line
                assert '"' + "/tmp/ws $(touch pwned)" not in line, line
