"""The repair of grouped invoice items, as text: running it is ``tools/verify_grouped_invoice_lines.py``."""

from __future__ import annotations

from odoo_dwg import lockdates, ungroup


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


def test_a_reused_source_item_is_never_given_an_amount():
    sql = ungroup.ungroup_sql()
    assert "column_name = 'aml_matched'" in sql
    assert "WHERE il.id = z.old_invoice_line_id AND il.aml_matched" in sql
    # Found before the groups, so the zero-amount lines are known when the groups are built.
    assert sql.index("CREATE TEMP TABLE odwg_fk") < sql.index("CREATE TEMP TABLE odwg_grp")


def test_what_a_linked_record_adds_up_to_is_checked():
    sql = ungroup.ungroup_sql()
    assert "check failed: what a link adds up to changed" in sql
    assert sql.index("CREATE TEMP TABLE odwg_b_sum") < sql.index("DELETE FROM account_move_line WHERE id IN")
    assert "account_analytic_account_account_move_line_rel" in ungroup.OWN_LINK_TABLES


def test_a_paid_invoice_of_a_closed_period_keeps_openupgrades_result():
    sql = ungroup.ungroup_sql()
    assert f"AND ({lockdates.after_lock('m')} OR m.amount_residual <> 0);" in sql
    assert f"AND NOT ({lockdates.after_lock('m')} OR m.amount_residual <> 0);" in sql
    assert "paid invoice(s) of closed periods kept as OpenUpgrade left them" in sql
