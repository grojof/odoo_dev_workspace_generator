"""The stock valuation alignment: when it applies, what it refuses, where the driver runs it."""

from __future__ import annotations

from odoo_dwg import templates, valuation
from odoo_dwg.models import MigrationEnv


def test_it_applies_from_a_source_without_layers_to_18():
    assert valuation.applies(12, 18) and valuation.applies(11, 19)
    assert not valuation.applies(13, 18) and not valuation.applies(12, 17)


def test_the_script_uses_odoos_own_rules_and_refuses_what_would_post_or_rewrite_costs():
    script = valuation.ALIGN
    compile(script, "align", "exec")
    assert "_should_be_valued()" in script and "_should_exclude_for_valuation()" in script
    assert 'product.valuation == "real_time"' in script
    assert 'product.cost_method == "fifo" or product.lot_valuated' in script
    assert script.index("(scalar(MOVES), scalar(COSTS)) != before") < script.index("cr.commit()")
    assert "cr.rollback()" in script and valuation.DESCRIPTION in script


def _driver(source: str = "12.0", target: str = "18.0") -> str:
    return templates.render_run_migration_sh(MigrationEnv(source=source, target=target))


def test_the_target_step_aligns_after_the_payments_and_before_its_checkpoint():
    sh = _driver()
    order = [sh.index(marker) for marker in (
        'mark "18.0" repair payments', "<<'ODWG_VALUATION'", 'mark "18.0" repair stock-valuation',
        'checkpoint "18.0"')]
    assert order == sorted(order)
    assert "ODWG_VALUATION_LIST=" in sh and "18.0-valuation-aligned.tsv" in sh


def test_a_source_with_layers_is_not_aligned():
    assert "ODWG_VALUATION" not in _driver(source="13.0")
