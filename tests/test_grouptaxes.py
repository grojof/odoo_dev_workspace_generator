"""Former group taxes: their repartition lines' accounts, set after the 13.0 step."""

from __future__ import annotations

from odoo_dwg import grouptaxes, templates
from odoo_dwg.models import MigrationEnv


def test_it_applies_to_a_source_up_to_12():
    assert grouptaxes.applies(12) and grouptaxes.applies(10)
    assert not grouptaxes.applies(13)


def test_a_line_takes_its_childs_account_and_only_when_it_has_none():
    sql = grouptaxes.repair_sql()
    assert "SET account_id = child.account_id" in sql
    # Matched as OpenUpgrade matches the journal items: document, type and sign.
    assert "(parent.invoice_tax_id IS NULL) = (child.invoice_tax_id IS NULL)" in sql
    assert "parent.repartition_type = 'tax' AND child.repartition_type = 'tax'" in sql
    assert "SIGN(tax.amount) = SIGN(parent.factor_percent)" in sql
    # An account the database already has stays, and nothing is set to nothing.
    assert "parent.account_id IS NULL AND child.account_id IS NOT NULL" in sql


def test_the_13_step_repairs_after_the_taxes_taken_back_and_before_its_checkpoint():
    sh = templates.render_run_migration_sh(MigrationEnv(source="12.0", target="18.0"))
    order = [sh.index(marker) for marker in (
        'mark "13.0" repair move-line-taxes', "<<'ODWG_GROUPTAX'",
        'mark "13.0" repair group-tax-accounts', 'neutralise "13.0"')]
    assert order == sorted(order)
    assert "13.0-group-tax-accounts.tsv" in sh
    assert sh.count("<<'ODWG_GROUPTAX'") == 1


def test_a_chain_from_13_does_not_repair():
    sh = templates.render_run_migration_sh(MigrationEnv(source="13.0", target="18.0"))
    assert "ODWG_GROUPTAX" not in sh
