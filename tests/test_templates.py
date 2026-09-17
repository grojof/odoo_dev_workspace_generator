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


def test_launch_has_one_config_per_version():
    cfg = WorkspaceConfig(name="acme", versions=["17.0", "18.0"])
    cfg.normalize_defaults()
    launch = json.loads(templates.render_vscode_launch(cfg))
    assert len(launch["configurations"]) == 2


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
    assert 'uv venv --seed --no-project --python 3.8 "' in script
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
