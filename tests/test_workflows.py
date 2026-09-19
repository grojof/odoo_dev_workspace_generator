"""The interactive workflows, driven with stubbed prompts: nothing runs, nothing
outside tmp_path is touched."""

from __future__ import annotations

import json

import pytest

from odoo_dwg import cli
from odoo_dwg.models import HOST_PYTHON, UV_PYTHON, WorkspaceConfig
from odoo_dwg.ui import strip_ansi
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


# --- how a plan reports while it runs -----------------------------------------


class _Result:
    def __init__(self, code=0, out=""):
        self.returncode, self.stdout, self.stderr = code, out, ""


def _plan():
    from odoo_dwg.models import Command

    return [Command("Clone something", "git clone x"),
            Command("Build something", "make"),
            Command("Break something", "false")]


@pytest.fixture()
def quiet():
    from odoo_dwg import system

    system.set_verbose(False)
    yield system
    system.set_verbose(False)


def test_quiet_shows_one_line_per_step_and_keeps_warnings(quiet, monkeypatch, capsys):
    outputs = {"git clone x": "Receiving objects: 100%\n",
               "make": "compiling\nWARNING: deprecated option\ndone\n"}
    monkeypatch.setattr(quiet, "run", lambda cmd, check=False: _Result(out=outputs.get(cmd, "")))
    monkeypatch.setattr(quiet, "run_streaming", lambda cmd: pytest.fail("quiet must not stream"))
    quiet.apply_commands(_plan()[:2])
    out = strip_ansi(capsys.readouterr().out)
    assert "[1/2] Clone something … " in out and "[2/2] Build something … " in out
    assert "WARNING: deprecated option" in out  # kept
    assert "Receiving objects" not in out  # ordinary chatter is not


def test_a_failing_step_prints_its_output_and_stops(quiet, monkeypatch, capsys):
    def run(cmd, check=False):
        return _Result(1, "context line\nboom: no such file\n") if cmd == "false" else _Result()

    monkeypatch.setattr(quiet, "run", run)
    with pytest.raises(RuntimeError, match="Failed running: false"):
        quiet.apply_commands(_plan())
    out = strip_ansi(capsys.readouterr().out)
    assert "boom: no such file" in out and "Command finished with code 1" in out


def test_verbose_streams_every_line(quiet, monkeypatch, capsys):
    streamed = []
    monkeypatch.setattr(quiet, "run", lambda cmd, check=False: pytest.fail("verbose must stream"))
    monkeypatch.setattr(quiet, "run_streaming",
                        lambda cmd: streamed.append(cmd) or _Result(out="live output\n"))
    quiet.set_verbose(True)
    quiet.apply_commands(_plan()[:1])
    assert streamed == ["git clone x"]
    assert "[1/1] Clone something" in strip_ansi(capsys.readouterr().out)


def _provision_facts(**kwargs):
    from odoo_dwg.provisioning import ProvisionFacts

    return ProvisionFacts(
        os_id="ubuntu", os_version_id="24.04", os_codename="noble",
        postgres_installed=True, postgres_running=True, dev_role="odoo", dev_role_exists=True,
        wkhtmltopdf="wkhtmltopdf 0.12.6 (with patched qt)", **kwargs,
    )


@pytest.mark.parametrize(
    "hba,narrowed",
    [
        ({"pg_hba_blanket_trust": True, "pg_hba_role_trusted": True}, True),
        ({"pg_hba_blanket_trust": False, "pg_hba_role_trusted": False}, True),
        ({"pg_hba_blanket_trust": False, "pg_hba_role_trusted": True}, False),
        ({}, False),  # unreadable: nothing is planned blind
    ],
)
def test_an_already_provisioned_host_still_gets_pg_hba_narrowed(monkeypatch, hba, narrowed):
    from odoo_dwg.workflows import provision

    planned: list = []
    monkeypatch.setattr(provision, "_is_root", lambda: True)
    monkeypatch.setattr(provision, "ask_text", lambda *a, **k: "odoo")
    monkeypatch.setattr(provision, "ask_bool", lambda *a, **k: False)
    monkeypatch.setattr(provision.provisioning, "gather_facts",
                        lambda dev_role=None, **k: _provision_facts(**hba))
    monkeypatch.setattr(provision, "preview_commands", lambda commands: planned.extend(commands))
    provision._apply()
    descriptions = " ".join(getattr(c, "description", "") for c in planned)
    assert ("pg_hba" in descriptions) is narrowed
    # The install steps are never re-planned on a host that already has them.
    assert "Install PostgreSQL" not in descriptions


def test_a_plan_step_never_reads_the_operators_terminal(monkeypatch):
    """A step inheriting stdin would swallow the answer to the next prompt while
    its own prompt sat hidden in the captured output."""
    import subprocess

    from odoo_dwg import system

    seen: dict = {}

    def fake_run(argv, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(system.subprocess, "run", fake_run)
    system.run("echo hi")
    assert seen["stdin"] is subprocess.DEVNULL


@pytest.mark.parametrize(
    "field,value",
    [
        ("working_db", 'x"; DROP DATABASE y --'),
        ("db_user", "odoo; DROP ROLE x"),
        ("db_host", "127.0.0.1\nsomething"),
        ("db_port", 0),
    ],
)
def test_a_hand_edited_migration_environment_is_refused(field, value):
    from odoo_dwg.models import MigrationEnv

    env = MigrationEnv(source="16.0", target="18.0", **{field: value})
    with pytest.raises(ValueError) as excinfo:
        env.validate()
    assert field in str(excinfo.value)


def test_a_sane_migration_environment_validates():
    from odoo_dwg.models import MigrationEnv

    MigrationEnv(source="16.0", target="18.0", interpreter_overrides={"17.0": "3.10"}).validate()
