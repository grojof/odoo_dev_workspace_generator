"""Editor configuration for the official Odoo language server (OdooLS).

These guard the promise that makes the file safe to emit at all: only the four
documented minimal keys, absolute paths, no template variables — because the
schema OdooLS validates against is strict and changes between releases. Whether
those keys are still accepted upstream is checked by
``tools/verify_odools_config.py``, which needs the network and is not a test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odoo_dwg import planners, templates
from odoo_dwg.models import WorkspaceConfig


def _cfg(tmp_path: Path, monkeypatch, **kw) -> WorkspaceConfig:
    monkeypatch.setattr(WorkspaceConfig, "base_dir", str(tmp_path / "workspaces"))
    cfg = WorkspaceConfig(name="acme", versions=kw.pop("versions", ["17.0", "18.0"]), **kw)
    cfg.normalize_defaults()
    return cfg


def _parse(text: str) -> dict:
    tomllib = pytest.importorskip("tomllib")  # stdlib from 3.11; the floor is 3.10
    return tomllib.loads(text)


def test_addons_dirs_without_core_is_the_conf_path_minus_core(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch, oca_repos=["web", "server-tools"])
    for version in cfg.versions:
        full = [str(p) for p in cfg.addons_dirs(version)]
        assert cfg.addons_path(version).split(",") == full
        # One list, two views: the language server's is the conf's without core.
        assert [str(p) for p in cfg.addons_dirs(version, include_core=False)] == full[:-1]
        assert full[-1] == str(cfg.odoo_clone_dir(version) / "addons")


def test_one_profile_per_version_with_exactly_the_minimal_keys(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch, oca_repos=["web"])
    parsed = _parse(templates.render_odools_toml(cfg))
    profiles = parsed["config"]
    assert [p["name"] for p in profiles] == ["acme 17.0", "acme 18.0"]
    for profile, version in zip(profiles, cfg.versions, strict=True):
        assert tuple(profile) == templates.ODOOLS_KEYS
        assert profile["odoo_path"] == str(cfg.odoo_clone_dir(version))
        assert profile["python_path"] == str(cfg.venv_dir(version) / "bin" / "python")
        assert profile["addons_paths"] == [
            str(p) for p in cfg.addons_dirs(version, include_core=False)
        ]


def test_core_addons_come_from_odoo_path_not_the_addon_list(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch, versions=["18.0"])
    profile = _parse(templates.render_odools_toml(cfg))["config"][0]
    assert str(cfg.odoo_clone_dir("18.0") / "addons") not in profile["addons_paths"]


def test_paths_are_absolute_and_free_of_template_variables(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch, oca_repos=["web"])
    text = templates.render_odools_toml(cfg)
    # No ${workspaceFolder}, $version, $autoDetectAddons, ... — only literal paths.
    assert "$" not in text
    for profile in _parse(text)["config"]:
        paths = [profile["odoo_path"], profile["python_path"], *profile["addons_paths"]]
        assert all(Path(p).is_absolute() for p in paths)


def test_paths_with_awkward_characters_survive_quoting(tmp_path, monkeypatch):
    # A quote and a backslash in the base directory must round-trip through TOML.
    odd = tmp_path / 'we"ird\\dir'
    monkeypatch.setattr(WorkspaceConfig, "base_dir", str(odd))
    cfg = WorkspaceConfig(name="acme", versions=["18.0"])
    cfg.normalize_defaults()
    profile = _parse(templates.render_odools_toml(cfg))["config"][0]
    assert profile["odoo_path"] == str(cfg.odoo_clone_dir("18.0"))


def test_the_tree_plan_writes_odools_toml_and_no_jsconfig(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    commands = [c.command for c in planners.plan_workspace_tree(cfg)]
    assert any(str(cfg.odools_file) in c for c in commands)
    assert not any("jsconfig" in c for c in commands)


def test_the_official_extension_is_recommended_not_the_community_one():
    recommended = json.loads(templates.render_vscode_extensions())["recommendations"]
    assert "Odoo.odoo" in recommended
    assert "trinhanhngoc.vscode-odoo" not in recommended
    # The Python extension stays: debugging and interpreter selection need it.
    assert "ms-python.python" in recommended and "ms-python.debugpy" in recommended


def test_python_is_analysed_by_one_server_only(tmp_path, monkeypatch):
    settings = json.loads(templates.render_vscode_settings(_cfg(tmp_path, monkeypatch)))
    assert settings["python.languageServer"] == "None"


def test_the_reviewed_release_is_recorded():
    major, minor, patch = (int(part) for part in templates.ODOOLS_REVIEWED_VERSION.split("."))
    assert (major, minor, patch) >= (1, 4, 0)


def test_versions_the_language_server_refuses_get_no_profile(tmp_path, monkeypatch):
    # OdooLS supports Odoo 14 and above; a 13 profile could only fail.
    cfg = _cfg(tmp_path, monkeypatch, versions=["13.0", "18.0"])
    text = templates.render_odools_toml(cfg)
    assert "No profile for 13.0" in text
    assert [p["name"] for p in _parse(text)["config"]] == ["acme 18.0"]


def test_a_workspace_with_no_supported_version_gets_no_file(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch, versions=["12.0"])
    commands = [c.command for c in planners.plan_workspace_tree(cfg)]
    assert not any(str(cfg.odools_file) in c for c in commands)
    # ...and the workspace README does not advertise a file that is not there.
    assert "odools.toml" not in templates.render_workspace_readme(cfg)


def test_the_readme_lists_the_file_when_it_exists(tmp_path, monkeypatch):
    readme = templates.render_workspace_readme(_cfg(tmp_path, monkeypatch, versions=["18.0"]))
    assert "odools.toml" in readme and "Odoo.odoo" in readme
