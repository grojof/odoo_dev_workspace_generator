"""The interactive workflows, driven with stubbed prompts: nothing runs, nothing
outside tmp_path is touched."""

from __future__ import annotations

import json

import pytest

from odoo_dwg import cli
from odoo_dwg.models import HOST_PYTHON, UV_PYTHON, WorkspaceConfig
from odoo_dwg.workflows import common, workspace


@pytest.fixture()
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(WorkspaceConfig, "base_dir", str(tmp_path))
    return tmp_path


def _write_profile(base, name, **profile):
    root = base / name
    root.mkdir(parents=True, exist_ok=True)
    (root / "workspace.json").write_text(json.dumps({"name": name, **profile}))
    return root / "workspace.json"


# --- loading profiles ---------------------------------------------------------


def test_a_valid_profile_loads_normalized(base):
    _write_profile(base, "acme", versions=["19.0", "18.0"])
    cfg = workspace._load_existing("acme")
    assert cfg is not None and cfg.versions == ["18.0", "19.0"] and cfg.db_user == "odoo"


@pytest.mark.parametrize("profile", [
    {"versions": ["18.0$(touch /tmp/p)"]},
    {"versions": ["18.0"], "oca_repos": ["../../etc"]},
    {"versions": ["18.0"], "db_host": "x\nadmin_passwd = y"},
    {"versions": ["18.0"], "db_port": "5432"},
])
def test_a_manipulated_profile_is_refused_on_manage(base, capsys, profile):
    _write_profile(base, "acme", **profile)
    assert workspace._load_existing("acme") is None
    assert "Cannot use the profile" in capsys.readouterr().out


def test_a_profile_naming_another_workspace_is_refused(base, capsys):
    _write_profile(base, "acme", versions=["18.0"])
    (base / "acme" / "workspace.json").write_text(json.dumps({"name": "other", "versions": ["18.0"]}))
    assert workspace._load_existing("acme") is None
    assert "names another workspace" in capsys.readouterr().out


def test_malformed_json_is_reported_not_raised(base, capsys):
    path = _write_profile(base, "acme", versions=["18.0"])
    path.write_text("{not json")
    assert workspace._load_existing("acme") is None
    assert "Cannot use the profile" in capsys.readouterr().out


# --- add a version ------------------------------------------------------------


def _loaded(base, versions=("18.0",)):
    _write_profile(base, "acme", versions=list(versions))
    return workspace._load_existing("acme")


def test_add_version_changes_nothing_until_its_plan_ran(base, monkeypatch):
    cfg = _loaded(base)
    monkeypatch.setattr(workspace, "ask_text", lambda *a, **k: "19.0")
    monkeypatch.setattr(workspace, "_plan_added_version", lambda candidate, version: False)
    workspace._add_version(cfg)
    assert cfg.versions == ["18.0"]  # declined or failed: untouched
    monkeypatch.setattr(workspace, "_plan_added_version", lambda candidate, version: True)
    workspace._add_version(cfg)
    assert cfg.versions == ["18.0", "19.0"]


@pytest.mark.parametrize("answer", ["19", "20.0", "19.0$(id)"])
def test_add_version_refuses_a_bad_version_before_planning(base, monkeypatch, capsys, answer):
    cfg = _loaded(base)
    monkeypatch.setattr(workspace, "ask_text", lambda *a, **k: answer)
    monkeypatch.setattr(workspace, "_plan_added_version",
                        lambda *a: pytest.fail("must not plan an invalid version"))
    workspace._add_version(cfg)
    assert cfg.versions == ["18.0"] and "invalid Odoo version" in capsys.readouterr().out


# --- interpreters read back from existing venvs ---------------------------------


def test_existing_interpreters_come_from_each_venvs_pyvenv_cfg(base, monkeypatch):
    cfg = _loaded(base, ("14.0", "18.0"))
    monkeypatch.setattr(workspace, "detect_python_version", lambda: "3.12")
    venv14 = cfg.venv_dir("14.0")
    venv14.mkdir(parents=True)
    (venv14 / "pyvenv.cfg").write_text("home = /x\nuv = 0.12\nversion_info = 3.8\n")
    choices = workspace._existing_interpreters(cfg)
    assert (choices["14.0"].python, choices["14.0"].source) == ("3.8", UV_PYTHON)
    # No venv yet: the default for this host.
    assert (choices["18.0"].python, choices["18.0"].source) == ("3.12", HOST_PYTHON)


# --- phrase-gated database change -----------------------------------------------


def test_mail_redirect_needs_a_valid_name_and_the_phrase(monkeypatch, capsys):
    applied = []
    monkeypatch.setattr(common, "apply_if_confirmed", lambda commands: applied.append(commands))
    monkeypatch.setattr(common, "ask_text", lambda *a, **k: "acme;drop")
    monkeypatch.setattr(common, "confirm_with_phrase",
                        lambda *a: pytest.fail("an invalid name must stop before the phrase"))
    common.redirect_mail("127.0.0.1", 5432, "odoo")
    assert "Invalid database name" in capsys.readouterr().out
    monkeypatch.setattr(common, "ask_text", lambda *a, **k: "acme_copy")
    monkeypatch.setattr(common, "confirm_with_phrase", lambda *a: False)
    common.redirect_mail("127.0.0.1", 5432, "odoo")
    assert applied == []  # no phrase, no change
    monkeypatch.setattr(common, "confirm_with_phrase", lambda *a: True)
    common.redirect_mail("127.0.0.1", 5432, "odoo")
    assert len(applied) == 1 and "-d acme_copy" in applied[0][0].command


# --- the CLI reports instead of crashing ------------------------------------------


@pytest.mark.parametrize("error", [ValueError("bad value"), OSError("unreadable"),
                                   TypeError("wrong type"), RuntimeError("step failed")])
def test_cli_reports_errors_instead_of_a_traceback(monkeypatch, capsys, error):
    def boom():
        raise error

    monkeypatch.setattr(cli, "workspace_menu", boom)
    assert cli.main(["workspace", "--lang", "en"]) == 1
    assert "The operation did not complete" in capsys.readouterr().out
