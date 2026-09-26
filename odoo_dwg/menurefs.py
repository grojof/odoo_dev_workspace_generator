"""Rows that point at menus, kept at the source restore and put back at the target step.

A module outside Odoo's core can reference menus through a many2many table. A module that hides menus
from some users or groups, for example, stores one row per user or group and menu. When the chain deletes
a menu, PostgreSQL deletes those rows with it (``ON DELETE CASCADE``), and nothing says so. On the first
client's database, one user's hidden customer invoices came back visible after the chain.

At the source restore the driver keeps every row of each two-column table with a foreign key to
``ir_ui_menu``, with the menu's external id and the table on the other side. ``ir_ui_menu_group_rel`` is
left out: it holds the groups each module declares on its menus, which every module update rewrites from
that module's data. At the target step, every kept row that is missing is put back. The menu is found by
its external id, or through :data:`SUCCESSORS` for the menus the chain replaced. Anything that cannot be
put back is listed.

Pure: this module holds SQL; the migration driver runs it.
"""

from __future__ import annotations

KEPT = "odwg_kept_menu_ref"
#: Odoo's own menu groups: module data, rewritten on every module update.
LEFT_OUT = "ir_ui_menu_group_rel"

#: Menus the chain deletes, mapped to a successor that opens the same documents, or to ``None``. The
#: evidence is cited for each one; a deleted menu missing from here is listed for the operator to decide.
SUCCESSORS: dict[str, str | None] = {
    # OpenUpgrade 13.0 account/13.0.1.1/openupgrade_analysis_work.txt: DEL the four invoice menus, NEW
    # the account.move ones. 12.0 account_invoice_view.xml: action_invoice_tree1 has the domain
    # type = out_invoice; 18.0 account_move_views.xml: action_move_out_invoice_type has
    # default_move_type out_invoice. The other three pair up the same way, one type each.
    "account.menu_action_invoice_tree1": "account.menu_action_move_out_invoice_type",
    "account.menu_action_invoice_out_refund": "account.menu_action_move_out_refund_type",
    "account.menu_action_invoice_tree2": "account.menu_action_move_in_invoice_type",
    "account.menu_action_invoice_in_refund": "account.menu_action_move_in_refund_type",
    # OpenUpgrade 16.0 sale/16.0.1.2/upgrade_analysis.txt: DEL; 17.0 sale/17.0.1.2: NEW
    # sale.menu_reporting_sales. Both open sale.action_order_report_all.
    "sale.menu_report_product_all": "sale.menu_reporting_sales",
    # OpenUpgrade 13.0 purchase/13.0.1.2/openupgrade_analysis_work.txt: DEL. From 13.0 the Purchase app
    # has no bills menu; the Invoicing app's is another app's menu, so it is not a successor.
    "purchase.menu_procurement_management_pending_invoice": None,
}


def applies(source_major: int, target_major: int) -> bool:
    return source_major < target_major


def keep_sql() -> str:
    """Run on the restored source, into a table of the tool's own."""
    return f"""\
DO $odwg$
DECLARE
  t record;
BEGIN
  DROP TABLE IF EXISTS {KEPT};
  CREATE TABLE {KEPT} (rel_table text, menu_column text, other_column text, other_table text,
    other_id integer, menu_id integer, menu_xmlid text);
  FOR t IN
    SELECT r.relname AS rel, a.attname AS menu_col, o.attname AS other_col,
           oc.relname AS other_table
      FROM pg_constraint c
      JOIN pg_class r ON r.oid = c.conrelid
      JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
      JOIN pg_attribute o ON o.attrelid = c.conrelid AND o.attnum > 0 AND NOT o.attisdropped
        AND o.attnum <> a.attnum
      LEFT JOIN pg_constraint f ON f.conrelid = c.conrelid AND f.contype = 'f'
        AND f.conkey[1] = o.attnum
      LEFT JOIN pg_class oc ON oc.oid = f.confrelid
     WHERE c.contype = 'f' AND c.confrelid = 'ir_ui_menu'::regclass
       AND c.conrelid <> 'ir_ui_menu'::regclass AND r.relname <> '{LEFT_OUT}'
       AND (SELECT count(*) FROM pg_attribute x WHERE x.attrelid = c.conrelid AND x.attnum > 0
            AND NOT x.attisdropped) = 2
     ORDER BY r.relname
  LOOP
    IF t.other_table IS NULL THEN
      RAISE NOTICE '[keep] menu references: %.% has no foreign key, % not kept',
        t.rel, t.other_col, t.rel;
      CONTINUE;
    END IF;
    EXECUTE format(
      'INSERT INTO {KEPT} SELECT %L, %L, %L, %L, r.%I, r.%I, '
      '(SELECT d.module || ''.'' || d.name FROM ir_model_data d WHERE d.model = ''ir.ui.menu'' '
      'AND d.res_id = r.%I ORDER BY d.id LIMIT 1) FROM %I r',
      t.rel, t.menu_col, t.other_col, t.other_table, t.other_col, t.menu_col, t.menu_col, t.rel);
  END LOOP;
  RAISE NOTICE '[keep] menu references: % rows in % tables',
    (SELECT count(*) FROM {KEPT}), (SELECT count(DISTINCT rel_table) FROM {KEPT});
END
$odwg$;
"""


def _successors_values() -> str:
    def lit(value: str | None) -> str:
        return "NULL" if value is None else f"'{value}'"
    return ",\n  ".join(f"({lit(old)}, {lit(new)})" for old, new in sorted(SUCCESSORS.items()))


def restore_sql() -> str:
    """Put back every kept row that is missing. One transaction; prints
    ``kind<TAB>table<TAB>other id<TAB>menu<TAB>detail`` per row put back or left."""
    return f"""\
BEGIN;
CREATE TEMP TABLE odwg_menu_succ (old text PRIMARY KEY, new text);
INSERT INTO odwg_menu_succ VALUES
  {_successors_values()};
CREATE TEMP TABLE odwg_menu_list (kind text, rel_table text, other_id integer, menu text,
  detail text);
DO $odwg$
DECLARE
  k record;
  target integer;
  via text;
  ok boolean;
  present integer := 0;
BEGIN
  FOR k IN SELECT DISTINCT * FROM {KEPT} ORDER BY rel_table, other_id, menu_xmlid, menu_id LOOP
    IF to_regclass(quote_ident(k.rel_table)) IS NULL THEN
      INSERT INTO odwg_menu_list VALUES ('table-gone', k.rel_table, k.other_id,
        coalesce(k.menu_xmlid, k.menu_id::text), 'the table is not in the target');
      CONTINUE;
    END IF;
    target := NULL;
    via := NULL;
    IF k.menu_xmlid IS NULL THEN
      SELECT id INTO target FROM ir_ui_menu WHERE id = k.menu_id;
      IF target IS NULL THEN
        INSERT INTO odwg_menu_list VALUES ('no-successor', k.rel_table, k.other_id,
          k.menu_id::text, 'a menu without an external id, gone');
        CONTINUE;
      END IF;
    ELSE
      SELECT d.res_id INTO target FROM ir_model_data d JOIN ir_ui_menu m ON m.id = d.res_id
       WHERE d.model = 'ir.ui.menu' AND d.module || '.' || d.name = k.menu_xmlid
       ORDER BY d.id LIMIT 1;
      IF target IS NULL THEN
        SELECT s.new INTO via FROM odwg_menu_succ s WHERE s.old = k.menu_xmlid;
        IF via IS NOT NULL THEN
          SELECT d.res_id INTO target FROM ir_model_data d JOIN ir_ui_menu m ON m.id = d.res_id
           WHERE d.model = 'ir.ui.menu' AND d.module || '.' || d.name = via
           ORDER BY d.id LIMIT 1;
        END IF;
        IF target IS NULL THEN
          INSERT INTO odwg_menu_list VALUES ('no-successor', k.rel_table, k.other_id,
            k.menu_xmlid, CASE
              WHEN via IS NOT NULL THEN 'its successor ' || via || ' is not in the target'
              WHEN EXISTS (SELECT 1 FROM odwg_menu_succ s WHERE s.old = k.menu_xmlid)
                THEN 'gone; declared without a successor'
              ELSE 'gone; no successor declared' END);
          CONTINUE;
        END IF;
      END IF;
    END IF;
    ok := false;
    IF to_regclass(quote_ident(k.other_table)) IS NOT NULL THEN
      EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I WHERE id = $1)', k.other_table)
        INTO ok USING k.other_id;
    END IF;
    IF NOT ok THEN
      INSERT INTO odwg_menu_list VALUES ('other-gone', k.rel_table, k.other_id,
        coalesce(k.menu_xmlid, k.menu_id::text), k.other_table || ' ' || k.other_id || ' is gone');
      CONTINUE;
    END IF;
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I WHERE %I = $1 AND %I = $2)',
      k.rel_table, k.menu_column, k.other_column) INTO ok USING target, k.other_id;
    IF ok THEN
      present := present + 1;
      CONTINUE;
    END IF;
    EXECUTE format('INSERT INTO %I (%I, %I) VALUES ($1, $2)',
      k.rel_table, k.menu_column, k.other_column) USING target, k.other_id;
    INSERT INTO odwg_menu_list VALUES (
      CASE WHEN via IS NULL THEN 'restored' ELSE 'restored-successor' END,
      k.rel_table, k.other_id, coalesce(k.menu_xmlid, k.menu_id::text),
      CASE WHEN via IS NULL THEN 'menu ' || target
           ELSE 'through its successor ' || via || ' (menu ' || target || ')' END);
  END LOOP;
  RAISE NOTICE '[repair] menu references: % put back, % already there, % left',
    (SELECT count(*) FROM odwg_menu_list WHERE kind LIKE 'restored%'), present,
    (SELECT count(*) FROM odwg_menu_list WHERE kind NOT LIKE 'restored%');
END
$odwg$;
SELECT kind, rel_table, other_id, menu, detail FROM odwg_menu_list
 ORDER BY kind, rel_table, other_id, menu;
COMMIT;
"""
