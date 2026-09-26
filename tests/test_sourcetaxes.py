"""The source's journal-item taxes, kept and taken back, as text: running it is
``tools/verify_source_taxes.py``."""

from __future__ import annotations

from odoo_dwg import sourcetaxes


def test_it_applies_to_a_source_whose_invoices_openupgrade_13_rebuilds():
    assert sourcetaxes.applies(12) and sourcetaxes.applies(11)
    assert not sourcetaxes.applies(13)


def test_keeping_copies_the_relation_and_the_highest_journal_item():
    sql = sourcetaxes.keep_sql()
    assert f"CREATE TABLE {sourcetaxes.KEPT_TABLE} AS" in sql
    assert "FROM account_move_line_account_tax_rel" in sql
    assert f"CREATE TABLE {sourcetaxes.MAX_ID_TABLE} AS SELECT coalesce(max(id), 0)" in sql


def test_only_what_the_invoice_line_bore_and_the_source_item_did_not_is_taken_back():
    sql = sourcetaxes.take_back_sql()
    assert f"l.id <= (SELECT id FROM {sourcetaxes.MAX_ID_TABLE})" in sql
    assert "l.old_invoice_line_id IS NOT NULL" in sql
    assert f"NOT EXISTS (SELECT 1 FROM {sourcetaxes.KEPT_TABLE} k" in sql
    assert "EXISTS (SELECT 1 FROM account_invoice_line_tax t" in sql
    assert sql.count("\nBEGIN;\n") == 1 and sql.count("\nCOMMIT;\n") == 1
    assert sql.index("DELETE FROM account_move_line_account_tax_rel") < sql.index("COMMIT;")


def test_it_drops_its_tables_and_skips_without_them():
    sql = sourcetaxes.take_back_sql()
    assert f"DROP TABLE {sourcetaxes.KEPT_TABLE}, {sourcetaxes.MAX_ID_TABLE};" in sql
    assert "\\if :odwg_ready" in sql and "SKIPPED" in sql
