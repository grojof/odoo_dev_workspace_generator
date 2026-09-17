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
    assert states["Dev role (odoo)"] == "MISSING"
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
    assert states["Dev role (odoo)"] == "OK"
    assert states["wkhtmltopdf"] == "OK"


def test_supported_ubuntu_release_is_ok():
    rows = provision_rows(ProvisionFacts(os_id="ubuntu", os_version_id="22.04", os_codename="jammy"))
    states = _states(rows)
    assert states["Host release"] == "OK"
    assert "22.04" in next(d for _s, c, d in rows if c == "Host release")


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


def test_uv_and_docker_absent_are_informational():
    facts = ProvisionFacts(os_id="ubuntu", os_version_id="24.04")
    states = _states(provision_rows(facts))
    assert states["uv (interpreters)"] == "INFO"
    assert states["Docker (migration 12/13)"] == "INFO"


def test_docker_binary_ok_daemon_warn_with_detail():
    facts = ProvisionFacts(
        os_id="ubuntu",
        os_version_id="24.04",
        docker_binary=True,
        docker_daemon=False,
        docker_daemon_detail="permission denied while trying to connect",
    )
    rows = provision_rows(facts)
    states = _states(rows)
    assert states["Docker binary"] == "OK"
    assert states["Docker daemon"] == "WARN"
    detail = next(d for _s, c, d in rows if c == "Docker daemon")
    assert "permission denied" in detail


def test_docker_ready_lists_fallback_images():
    facts = ProvisionFacts(
        os_id="ubuntu",
        os_version_id="24.04",
        uv=True,
        docker_binary=True,
        docker_daemon=True,
        docker_images={"odoo:13.0": True, "odoo:12.0": False},
    )
    rows = provision_rows(facts)
    states = _states(rows)
    assert states["uv (interpreters)"] == "OK"
    assert states["Docker daemon"] == "OK"
    detail = next(d for _s, c, d in rows if c == "OpenUpgrade fallback images")
    assert "odoo:13.0 present" in detail and "odoo:12.0 not pulled" in detail


def test_unpatched_wkhtmltopdf_is_warn():
    facts = ProvisionFacts(os_id="ubuntu", os_version_id="24.04", wkhtmltopdf="wkhtmltopdf 0.12.6")
    states = _states(provision_rows(facts))
    assert states["wkhtmltopdf"] == "WARN"
