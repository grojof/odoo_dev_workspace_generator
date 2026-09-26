"""Rows that point at menus: kept at the source restore, put back at the target."""

from __future__ import annotations

from odoo_dwg import menurefs, templates
from odoo_dwg.models import MigrationEnv


def test_it_applies_to_any_chain():
    assert menurefs.applies(12, 13) and menurefs.applies(12, 18)
    assert not menurefs.applies(18, 18)


def test_the_source_keeps_two_column_menu_relations_but_odoos_own_groups():
    sql = menurefs.keep_sql()
    assert "c.confrelid = 'ir_ui_menu'::regclass" in sql
    assert "AND NOT x.attisdropped) = 2" in sql
    assert f"r.relname <> '{menurefs.LEFT_OUT}'" in sql and menurefs.LEFT_OUT == "ir_ui_menu_group_rel"
    assert "d.model = ''ir.ui.menu''" in sql


def test_every_successor_opens_the_same_documents():
    assert menurefs.SUCCESSORS["account.menu_action_invoice_tree1"] == \
        "account.menu_action_move_out_invoice_type"
    assert menurefs.SUCCESSORS["sale.menu_report_product_all"] == "sale.menu_reporting_sales"
    # Another app's menu is not a successor.
    assert menurefs.SUCCESSORS["purchase.menu_procurement_management_pending_invoice"] is None


def test_the_restore_inserts_only_what_is_missing_and_lists_the_rest():
    sql = menurefs.restore_sql()
    assert sql.startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;")
    assert "('account.menu_action_invoice_tree1', 'account.menu_action_move_out_invoice_type')" in sql
    assert "('purchase.menu_procurement_management_pending_invoice', NULL)" in sql
    for kind in ("restored", "restored-successor", "no-successor", "other-gone", "table-gone"):
        assert f"'{kind}'" in sql
    assert "SELECT EXISTS (SELECT 1 FROM %I WHERE %I = $1 AND %I = $2)" in sql


def _driver(source: str = "12.0", target: str = "18.0") -> str:
    return templates.render_run_migration_sh(MigrationEnv(source=source, target=target))


def test_the_driver_keeps_at_the_source_restore_and_restores_after_the_source_configuration():
    sh = _driver()
    fresh = sh.index("if ! have_ck 00_source; then")
    assert fresh < sh.index("<<'ODWG_KEEP_MENUS'") < sh.index("checkpoint 00_source")
    order = [sh.index(marker) for marker in (
        'mark "18.0" repair source-configuration', "<<'ODWG_MENUS'",
        'mark "18.0" repair menu-references', 'mark "18.0" repair module-states',
        'checkpoint "18.0"')]
    assert order == sorted(order)
    assert "menu-references-skipped" in sh and "18.0-menu-references.tsv" in sh


def test_a_target_before_18_still_keeps_and_restores():
    sh = _driver(target="16.0")
    assert "<<'ODWG_KEEP_MENUS'" in sh and "<<'ODWG_MENUS'" in sh
