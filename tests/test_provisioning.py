"""Unit tests for the pure provision-check row logic (no host probing)."""

from __future__ import annotations

from odoo_dwg.provisioning import ProvisionFacts, provision_rows


def _states(rows) -> dict[str, str]:
    # Map capability name → state for easy assertions.
    return {check: state for state, check, _detail in rows}


def test_bare_host_reports_missing():
    facts = ProvisionFacts(
        os_family="debian",
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
        os_family="debian",
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


def test_non_apt_family_is_warned():
    facts = ProvisionFacts(os_family="", os_codename="")
    states = _states(provision_rows(facts))
    assert states["Package family"] == "WARN"


def test_postgres_installed_not_running_is_warn():
    facts = ProvisionFacts(os_family="debian", postgres_installed=True, postgres_running=False)
    states = _states(provision_rows(facts))
    assert states["PostgreSQL"] == "WARN"


def test_unpatched_wkhtmltopdf_is_warn():
    facts = ProvisionFacts(os_family="debian", wkhtmltopdf="wkhtmltopdf 0.12.6")
    states = _states(provision_rows(facts))
    assert states["wkhtmltopdf"] == "WARN"
