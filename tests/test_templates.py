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
