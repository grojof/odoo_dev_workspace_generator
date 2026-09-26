"""The source configuration the chain changes: kept at the source restore, put back at the target."""

from __future__ import annotations

from odoo_dwg import sourceconfig, templates
from odoo_dwg.models import MigrationEnv


def test_it_applies_to_a_target_from_18():
    assert sourceconfig.applies(12, 18) and sourceconfig.applies(17, 19)
    assert not sourceconfig.applies(12, 17) and not sourceconfig.applies(18, 19)


def test_the_source_keeps_return_types_aliases_and_rules_with_their_xmlid():
    sql = sourceconfig.keep_sql()
    assert "SELECT id, return_picking_type_id FROM stock_picking_type" in sql
    assert "JOIN mail_alias a ON a.id = j.alias_id" in sql
    assert "d.module || '.' || d.name AS odwg_xmlid" in sql


def test_the_restore_archives_only_what_the_chain_created_and_nothing_uses():
    script = sourceconfig.RESTORE
    compile(script, "restore", "exec")
    assert "WHERE id > %s" in script and "c.confrelid = 'stock_picking_type'::regclass" in script
    assert "<> 'stock_warehouse'" in script
    # Default locations by Odoo's own compute, on the missing field only.
    assert 'Type.search([(field, "=", False)])' in script and "env.add_to_compute" in script


def test_the_rule_is_recreated_from_the_source_as_openupgrade_15_maps_it():
    script = sourceconfig.RESTORE
    assert sourceconfig.DEFAULT_RULE in script
    assert '"allow_payment_tolerance": total' in script
    assert '"payment_tolerance_param": 100.0 - (param or 0.0)' in script
    assert '"auto_reconcile": auto' in script


def _driver(source: str = "12.0", target: str = "18.0") -> str:
    return templates.render_run_migration_sh(MigrationEnv(source=source, target=target))


def test_the_driver_keeps_at_the_source_restore_and_restores_after_the_tax_grids():
    sh = _driver()
    fresh = sh.index("if ! have_ck 00_source; then")
    assert fresh < sh.index("<<'ODWG_KEEP_CONFIG'") < sh.index("checkpoint 00_source")
    order = [sh.index(marker) for marker in (
        'mark "18.0" repair tax-grids', "<<'ODWG_CONFIG'", 'mark "18.0" repair source-configuration',
        'checkpoint "18.0"')]
    assert order == sorted(order)
    assert "source-configuration-skipped" in sh


def test_a_target_before_18_neither_keeps_nor_restores():
    sh = _driver(target="17.0")
    assert "ODWG_KEEP_CONFIG" not in sh and "ODWG_CONFIG" not in sh
