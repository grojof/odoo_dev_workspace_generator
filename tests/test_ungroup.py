"""The repair of grouped invoice items, as text: running it is ``tools/verify_grouped_invoice_lines.py``."""

from __future__ import annotations

from odoo_dwg import ungroup


def test_it_applies_to_a_source_that_can_group_and_a_target_that_shows_the_items():
    assert ungroup.applies(12, 18) and ungroup.applies(11, 16)
    assert not ungroup.applies(13, 18) and not ungroup.applies(12, 15)


def test_it_commits_once_and_only_after_its_checks():
    sql = ungroup.ungroup_sql()
    assert sql.count("\nBEGIN;\n") == 1 and sql.count("\nCOMMIT;\n") == 1
    assert sql.index("check failed: a balance per account and partner changed") < sql.index("COMMIT;")
    for check in ("a move is not balanced", "a tax base changed", "an invoice''s amounts changed",
                  "a link to a grouped item was lost"):
        assert f"check failed: {check}" in sql


def test_an_amount_moves_only_inside_one_move_account_and_set_of_taxes():
    sql = ungroup.ungroup_sql()
    assert "USING (move_id, account_id, tk)" in sql
    # The direction is the document's, never the grouped item's sign (a group can net to 0).
    assert "CASE WHEN m.move_type IN ('in_invoice', 'out_refund') THEN 1 ELSE -1 END d" in sql
    assert "sign(" not in sql


def test_the_lines_own_tables_are_never_copied_and_unknown_references_keep_their_group():
    sql = ungroup.ungroup_sql()
    for table in ungroup.OWN_LINK_TABLES:
        assert f"'{table}'" in sql
    for table, column in ungroup.MOVABLE_REFERENCES:
        assert f"('{table}', '{column}')" in sql
    assert "'referenced by ' || fk.tbl || '.' || fk.col" in sql


def test_it_does_nothing_without_openupgrade_13_columns():
    sql = ungroup.ungroup_sql()
    assert "\\if :odwg_ready" in sql and "not applicable" in sql
