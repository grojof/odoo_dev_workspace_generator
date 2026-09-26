"""The tax grids' refresh: when it applies, what it relies on, where the driver runs it."""

from __future__ import annotations

from odoo_dwg import taxgrids, templates
from odoo_dwg.models import MigrationEnv


def test_it_applies_to_a_chain_that_crosses_17():
    assert taxgrids.applies(12, 18) and taxgrids.applies(16, 17)
    assert not taxgrids.applies(17, 18) and not taxgrids.applies(12, 16)


def test_the_script_uses_the_chart_templates_own_reload_restricted_to_taxes():
    script = taxgrids.REFRESH
    compile(script, "refresh", "exec")
    assert 'data = {"account.tax": data.get("account.tax", {})}' in script
    assert "CT._pre_reload_data(company, template_data, data, force_create=False)" in script
    assert "CT._load_data(data)" in script
    # The company's settings are not rewritten from the template.
    assert "_pre_load_data" not in script and "_post_load_data" not in script


def test_journal_items_are_regridded_only_on_invoices_and_nothing_moves():
    script = taxgrids.REFRESH
    assert "m.move_type <> 'entry'" in script
    assert "THEN 'refund' ELSE 'invoice' END" in script
    assert "g.applicability = 'taxes'" in script
    assert script.index("rows(AMOUNTS)[0][0] != before") < script.index("cr.commit()")
    assert "e.engine = 'tax_tags'" in script and "SET active = false" in script


def _driver(source: str = "12.0", target: str = "18.0") -> str:
    return templates.render_run_migration_sh(MigrationEnv(source=source, target=target))


def test_the_target_step_refreshes_after_the_valuation_and_before_its_checkpoint():
    sh = _driver()
    order = [sh.index(marker) for marker in (
        'mark "18.0" repair stock-valuation', "<<'ODWG_TAXGRIDS'", 'mark "18.0" repair tax-grids',
        'checkpoint "18.0"')]
    assert order == sorted(order)
    assert "ODWG_TAXGRIDS_LIST=" in sh and "18.0-tax-grids.tsv" in sh


def test_a_chain_from_17_does_not_refresh():
    assert "ODWG_TAXGRIDS" not in _driver(source="17.0")
