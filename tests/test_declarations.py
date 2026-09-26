"""Filed declarations kept and put back, as text: running it is ``tools/verify_filed_declarations.py``."""

from __future__ import annotations

from odoo_dwg import declarations


def test_keeping_copies_the_boxes_their_links_and_the_maps_they_point_at():
    sql = declarations.keep_sql()
    assert "CREATE TABLE odwg_kept_aeat_tax_line AS SELECT * FROM l10n_es_aeat_tax_line;" in sql
    assert "WHERE id IN (SELECT map_line_id FROM odwg_kept_aeat_tax_line)" in sql
    assert "WHERE id IN (SELECT map_parent_id FROM odwg_kept_aeat_map_tax_line)" in sql
    assert f"FROM {declarations.LINK_TABLE};" in sql


def test_putting_back_goes_parents_first_and_checks_every_box():
    sql = declarations.restore_sql()
    order = [sql.index(f"('{table}', '{kept}')") for table, kept in declarations.KEPT]
    assert order == sorted(order)
    assert "WHERE NOT EXISTS (SELECT 1 FROM %I x WHERE x.id = k.id)" in sql
    assert "check failed: a box the source held is missing or changed" in sql
    assert sql.count("\nBEGIN;\n") == 1 and sql.count("\nCOMMIT;\n") == 1
    assert "\\if :odwg_ready" in sql and "SKIPPED" in sql
