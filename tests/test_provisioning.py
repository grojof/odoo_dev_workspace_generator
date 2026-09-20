"""Unit tests for the pure provision-check row logic (no host probing)."""

from __future__ import annotations

from odoo_dwg.provisioning import ProvisionFacts, provision_rows


def _states(rows) -> dict[str, str]:
    # Map capability name → state for easy assertions.
    return {check: state for state, check, _detail in rows}


def test_bare_host_reports_missing():
    facts = ProvisionFacts(
        os_id="ubuntu",
        os_version_id="24.04",
        os_codename="noble",
        build_deps_missing=["libpq-dev", "libxml2-dev"],
        postgres_installed=False,
        dev_role="odoo",
        dev_role_exists=False,
        wkhtmltopdf=None,
    )
    states = _states(provision_rows(facts))
    assert states["Odoo build dependencies"] == "MISSING"
    assert states["PostgreSQL"] == "MISSING"
    assert states["Development role (odoo)"] == "MISSING"
    assert states["wkhtmltopdf"] == "MISSING"


def test_ready_host_reports_ok():
    facts = ProvisionFacts(
        os_id="ubuntu",
        os_version_id="24.04",
        os_codename="noble",
        build_deps_missing=[],
        postgres_installed=True,
        postgres_running=True,
        dev_role="odoo",
        dev_role_exists=True,
        wkhtmltopdf="wkhtmltopdf 0.12.6 (with patched qt)",
        node=True,
        rtlcss=True,
    )
    states = _states(provision_rows(facts))
    assert states["Odoo build dependencies"] == "OK"
    assert states["PostgreSQL"] == "OK"
    assert states["Development role (odoo)"] == "OK"
    assert states["wkhtmltopdf"] == "OK"


def test_supported_ubuntu_release_is_ok():
    rows = provision_rows(ProvisionFacts(os_id="ubuntu", os_version_id="24.04", os_codename="noble"))
    states = _states(rows)
    assert states["Host release"] == "OK"
    assert "24.04" in next(d for _s, c, d in rows if c == "Host release")


def test_ubuntu_22_04_is_no_longer_supported():
    # Declared once, never validated on a real host - dropped like Debian.
    rows = provision_rows(ProvisionFacts(os_id="ubuntu", os_version_id="22.04", os_codename="jammy"))
    assert _states(rows)["Host release"] == "WARN"


def test_debian_is_no_longer_reported_as_supported():
    # The apt family used to pass; the matrix declares Ubuntu releases only.
    rows = provision_rows(
        ProvisionFacts(os_id="debian", os_version_id="12", os_pretty_name="Debian GNU/Linux 12")
    )
    states = _states(rows)
    assert states["Host release"] == "WARN"
    detail = next(d for _s, c, d in rows if c == "Host release")
    assert "Debian GNU/Linux 12" in detail and "Ubuntu 24.04 LTS" in detail


def test_unknown_host_is_reported_without_failing():
    rows = provision_rows(ProvisionFacts())
    states = _states(rows)
    assert states["Host release"] == "WARN"
    assert "unknown" in next(d for _s, c, d in rows if c == "Host release")


def test_postgres_version_below_the_floor_is_warned():
    # Odoo 19 requires PostgreSQL 13; a 12 server is short.
    rows = provision_rows(
        ProvisionFacts(
            os_id="ubuntu",
            os_version_id="24.04",
            postgres_installed=True,
            postgres_running=True,
            postgres_version=12,
            versions=["19.0"],
        )
    )
    states = _states(rows)
    assert states["PostgreSQL version"] == "WARN"
    detail = next(d for _s, c, d in rows if c == "PostgreSQL version")
    assert "12 is below the 13.0" in detail


def test_postgres_version_at_or_above_the_floor_is_ok():
    rows = provision_rows(
        ProvisionFacts(
            os_id="ubuntu",
            os_version_id="24.04",
            postgres_installed=True,
            postgres_running=True,
            postgres_version=16,
            versions=["19.0"],
        )
    )
    states = _states(rows)
    assert states["PostgreSQL version"] == "OK"
    assert "16" in next(d for _s, c, d in rows if c == "PostgreSQL version")


def test_no_postgres_version_row_when_the_server_is_not_running():
    rows = provision_rows(
        ProvisionFacts(os_id="ubuntu", os_version_id="24.04", postgres_installed=True)
    )
    assert "PostgreSQL version" not in _states(rows)


def test_uv_row_lists_the_interpreters_it_can_provide():
    rows = provision_rows(
        ProvisionFacts(
            os_id="ubuntu", os_version_id="24.04", uv=True, uv_pythons=["3.8", "3.10", "3.12"]
        )
    )
    detail = next(d for _s, c, d in rows if c == "uv (interpreters)")
    assert "3.8" in detail and "3.12" in detail


def test_host_python_row_is_informational():
    rows = provision_rows(
        ProvisionFacts(os_id="ubuntu", os_version_id="24.04", host_python="3.12")
    )
    assert _states(rows)["Host python3"] == "INFO"


def test_postgres_installed_not_running_is_warn():
    facts = ProvisionFacts(os_id="ubuntu", os_version_id="24.04", postgres_installed=True, postgres_running=False)
    states = _states(provision_rows(facts))
    assert states["PostgreSQL"] == "WARN"


def test_uv_absent_is_informational_and_no_container_row_exists():
    facts = ProvisionFacts(os_id="ubuntu", os_version_id="24.04")
    states = _states(provision_rows(facts))
    assert states["uv (interpreters)"] == "INFO"
    assert not [check for check in states if "Docker" in check]


def test_unpatched_wkhtmltopdf_is_warn():
    facts = ProvisionFacts(os_id="ubuntu", os_version_id="24.04", wkhtmltopdf="wkhtmltopdf 0.12.6")
    states = _states(provision_rows(facts))
    assert states["wkhtmltopdf"] == "WARN"


def test_apply_rejects_an_unsafe_role_before_probing_or_planning(monkeypatch, capsys):
    from odoo_dwg.workflows import provision

    monkeypatch.setattr(provision, "_is_root", lambda: True)
    monkeypatch.setattr(provision, "ask_text", lambda *a, **k: "odoo'; DROP DATABASE x; --")

    def _unexpected(*args, **kwargs):
        raise AssertionError("an unsafe role must stop apply before the host is probed")

    monkeypatch.setattr(provision.provisioning, "gather_facts", _unexpected)
    monkeypatch.setattr(provision.planners, "plan_postgresql", _unexpected)
    provision._apply()
    assert "Invalid PostgreSQL role" in capsys.readouterr().out


def test_an_unknown_role_is_a_warning_not_missing():
    facts = ProvisionFacts(os_id="ubuntu", os_version_id="24.04", postgres_installed=True,
                           postgres_running=True, dev_role="odoo", dev_role_exists=None)
    state = {check: (st, detail) for st, check, detail in provision_rows(facts)}["Development role (odoo)"]
    assert state[0] == "WARN" and "without sudo" in state[1]


def test_postgres_probes_never_prompt(monkeypatch):
    """Every probe command either needs no authentication or uses `sudo -n`."""
    from odoo_dwg import system

    seen: list[str] = []

    class _Done:
        def __init__(self, code=1, out=""):
            self.returncode, self.stdout, self.stderr = code, out, ""

    monkeypatch.setattr(system, "run", lambda cmd, check=False: seen.append(cmd) or _Done())
    monkeypatch.setattr(system, "command_ok", lambda cmd: seen.append(cmd) or False)
    monkeypatch.setattr(system, "has_tool", lambda name: False)
    system.postgres_running()
    system.detect_postgres_version()
    # The two that read as the server: both capture their output, so a password
    # prompt would hang the flow with nothing on screen.
    system.pg_hba_rules()
    system.psql_scalar("SELECT 1", "acme")
    assert system.db_role_exists("odoo") is None
    assert system.db_role_exists("bad role; x") is False
    for cmd in seen:
        assert "sudo -u" not in cmd, cmd
        if "sudo" in cmd:
            assert "sudo -n " in cmd, cmd
    assert any("pg_isready" in cmd for cmd in seen)
    assert any("-U odoo" in cmd and "-w" in cmd for cmd in seen)
    # Every psql here runs with -X: `~/.psqlrc` can hold a `\c otherdb` or a
    # `\! command`, and a probe's output is captured, so neither would be seen.
    for cmd in seen:
        if "psql" in cmd:
            assert "psql -X" in cmd, cmd


def _hba_row(**kwargs) -> tuple[str, str]:
    facts = ProvisionFacts(
        os_id="ubuntu", os_version_id="24.04", postgres_installed=True, dev_role="odoo", **kwargs
    )
    for state, check, detail in provision_rows(facts):
        if check == "PostgreSQL loopback auth":
            return state, detail
    raise AssertionError("no loopback auth row")


def test_blanket_loopback_trust_is_reported_so_apply_narrows_it():
    # The dangerous one: any local user may connect as postgres.
    state, detail = _hba_row(pg_hba_blanket_trust=True, pg_hba_role_trusted=True)
    assert state == "WARN"
    assert "odoo" in detail

    state, _ = _hba_row(pg_hba_blanket_trust=False, pg_hba_role_trusted=True)
    assert state == "OK"


def test_a_missing_role_trust_line_is_reported_without_alarm():
    state, _ = _hba_row(pg_hba_blanket_trust=False, pg_hba_role_trusted=False)
    assert state == "INFO"


def test_a_state_that_could_not_be_had_is_never_read_as_narrow():
    """Unreadable, or full of include directives: either way, not "narrow"."""
    state, detail = _hba_row()  # both None
    assert state == "WARN"
    assert "sudo" in detail and "stopped" in detail
