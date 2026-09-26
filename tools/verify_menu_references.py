#!/usr/bin/env python3
"""Keep the rows that point at menus and put them back, on a throwaway PostgreSQL.

The unit suite checks the SQL's text and where the driver runs it. This runs the keep on a
source-shaped database, simulates what the chain does, and runs the restore on it:

- the chain deletes a menu and creates its successor: the row comes back on the successor;
- it deletes a menu declared without a successor, and one no table declares: both listed, nothing
  inserted;
- it deletes a menu and creates it again under the same external id with a new id: the row comes back
  on the new id;
- a user is deleted: listed as gone, nothing inserted;
- a menu without an external id survives, and a row that survived is left as it is;
- Odoo's own menu groups and a table with more than two columns are not kept;
- a table the target no longer has: listed;
- a second run inserts nothing.

    python tools/verify_menu_references.py

Needs PostgreSQL server binaries. No network, no root.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_mail_capture import Cluster, _bindir  # noqa: E402

from odoo_dwg import menurefs  # noqa: E402

SCHEMA = """
    CREATE TABLE ir_ui_menu (id serial PRIMARY KEY, name varchar,
      parent_id integer REFERENCES ir_ui_menu ON DELETE RESTRICT);
    CREATE TABLE ir_model_data (id serial PRIMARY KEY, module varchar, name varchar, model varchar,
      res_id integer);
    CREATE TABLE res_users (id integer PRIMARY KEY);
    CREATE TABLE res_groups (id integer PRIMARY KEY);
    CREATE TABLE ir_ui_menu_res_users_hidden_rel (
      menu_id integer REFERENCES ir_ui_menu ON DELETE CASCADE,
      user_id integer REFERENCES res_users ON DELETE CASCADE);
    CREATE TABLE ir_ui_menu_group_restrict_rel (
      menu_id integer REFERENCES ir_ui_menu ON DELETE CASCADE,
      gres_id integer REFERENCES res_groups ON DELETE CASCADE);
    CREATE TABLE x_menu_note_rel (
      menu_id integer REFERENCES ir_ui_menu ON DELETE CASCADE,
      note_id integer REFERENCES res_groups ON DELETE CASCADE);
    CREATE TABLE ir_ui_menu_group_rel (
      menu_id integer REFERENCES ir_ui_menu ON DELETE CASCADE,
      gid integer REFERENCES res_groups ON DELETE CASCADE);
    CREATE TABLE wizard_ir_model_menu_create (id serial, name varchar,
      menu_id integer REFERENCES ir_ui_menu ON DELETE CASCADE);
"""

# Menus: 1 invoices (replaced), 2 bills of purchase (no successor), 3 a custom module's menu (no
# successor declared), 4 sales report (recreated under its xmlid), 5 kept, 6 made from the interface.
SOURCE = """
    INSERT INTO ir_ui_menu (id, name) VALUES (1, 'Invoices'), (2, 'Bills'), (3, 'Custom'),
      (4, 'Sales'), (5, 'Invoicing'), (6, 'Mine');
    INSERT INTO ir_model_data (module, name, model, res_id) VALUES
      ('account', 'menu_action_invoice_tree1', 'ir.ui.menu', 1),
      ('purchase', 'menu_procurement_management_pending_invoice', 'ir.ui.menu', 2),
      ('custom', 'menu_custom', 'ir.ui.menu', 3),
      ('sale', 'menu_sale_report', 'ir.ui.menu', 4),
      ('account', 'menu_finance', 'ir.ui.menu', 5);
    INSERT INTO res_users VALUES (7), (8), (9);
    INSERT INTO res_groups VALUES (20), (21);
    INSERT INTO ir_ui_menu_res_users_hidden_rel VALUES (1, 7), (2, 7), (3, 7), (4, 7), (5, 7),
      (6, 8), (1, 9);
    INSERT INTO ir_ui_menu_group_restrict_rel VALUES (5, 20);
    INSERT INTO x_menu_note_rel VALUES (1, 21);
    INSERT INTO ir_ui_menu_group_rel VALUES (1, 20);
    INSERT INTO wizard_ir_model_menu_create (name, menu_id) VALUES ('w', 1);
"""

# What the chain does: menus 1-4 deleted (cascading their rows), the invoices' successor created,
# the sales report created again under its xmlid, user 9 deleted, the custom table dropped.
CHAIN = """
    DELETE FROM ir_model_data WHERE res_id IN (1, 2, 3, 4);
    DELETE FROM ir_ui_menu WHERE id IN (1, 2, 3, 4);
    INSERT INTO ir_ui_menu (id, name) VALUES (40, 'Invoices'), (41, 'Sales');
    INSERT INTO ir_model_data (module, name, model, res_id) VALUES
      ('account', 'menu_action_move_out_invoice_type', 'ir.ui.menu', 40),
      ('sale', 'menu_sale_report', 'ir.ui.menu', 41);
    DELETE FROM res_users WHERE id = 9;
    DROP TABLE x_menu_note_rel;
"""


def _psql(cluster: Cluster, db: str, sql: str) -> subprocess.CompletedProcess[str]:
    """As the driver runs it: ``psql -X -q -At -F<TAB> -v ON_ERROR_STOP=1``, the SQL on stdin."""
    return subprocess.run(
        [str(cluster.bin / "psql"), "-X", "-q", "-At", "-F", "\t", "-v", "ON_ERROR_STOP=1",
         "-h", str(cluster.sock), "-p", str(cluster.port), "-U", "postgres", "-d", db, "-w"],
        input=sql, capture_output=True, text=True,
    )


def main() -> int:
    bindir = _bindir()
    if bindir is None:
        print("No PostgreSQL server binaries found under /usr/lib/postgresql.")
        return 1

    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        print(f"{'ok  ' if condition else 'FAIL'}  {label}")
        if not condition:
            failures.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory(prefix="odwg-menurefs-") as tmp:
        cluster = Cluster(Path(tmp), bindir)
        cluster.start()
        try:
            cluster.sql("CREATE DATABASE probe")
            for part in (SCHEMA, SOURCE):
                if (done := cluster.sql(part, "probe")).returncode != 0:
                    raise SystemExit(f"fixture failed: {done.stderr.strip()}")

            def value(sql: str) -> str:
                return cluster.value(sql, "probe")

            kept = _psql(cluster, "probe", menurefs.keep_sql())
            check("the keep runs", kept.returncode == 0, kept.stderr.strip())
            check("both relations and the custom one are kept, with their menus' xmlids",
                  value(f"SELECT count(*) FROM {menurefs.KEPT}") == "9"
                  and value(f"SELECT menu_xmlid FROM {menurefs.KEPT} WHERE other_id = 21")
                  == "account.menu_action_invoice_tree1", kept.stderr)
            check("Odoo's own menu groups and a wider table are not kept",
                  value(f"SELECT count(*) FROM {menurefs.KEPT} WHERE rel_table IN "
                        "('ir_ui_menu_group_rel', 'wizard_ir_model_menu_create')") == "0", "")

            if (done := cluster.sql(CHAIN, "probe")).returncode != 0:
                raise SystemExit(f"chain failed: {done.stderr.strip()}")
            ran = _psql(cluster, "probe", menurefs.restore_sql())
            rows = [line.split("\t") for line in ran.stdout.splitlines()]
            by = {(kind, table, int(other), menu): detail
                  for kind, table, other, menu, detail in rows}
            hidden = "ir_ui_menu_res_users_hidden_rel"

            check("the restore runs", ran.returncode == 0, ran.stderr.strip())
            check("a replaced menu comes back on its successor, and says so",
                  "account.menu_action_move_out_invoice_type" in by.get(
                      ("restored-successor", hidden, 7, "account.menu_action_invoice_tree1"), "")
                  and value(f"SELECT count(*) FROM {hidden} WHERE menu_id = 40 AND user_id = 7")
                  == "1", str(rows))
            check("a menu created again under its xmlid takes the row on its new id",
                  ("restored", hidden, 7, "sale.menu_sale_report") in by
                  and value(f"SELECT count(*) FROM {hidden} WHERE menu_id = 41") == "1", str(rows))
            check("a menu declared without a successor is listed, nothing inserted",
                  by.get(("no-successor", hidden, 7,
                          "purchase.menu_procurement_management_pending_invoice"))
                  == "gone; declared without a successor", str(rows))
            check("a menu no table declares is listed for the operator",
                  by.get(("no-successor", hidden, 7, "custom.menu_custom"))
                  == "gone; no successor declared", str(rows))
            check("a deleted user is listed as gone, nothing inserted",
                  ("other-gone", hidden, 9, "account.menu_action_invoice_tree1") in by, str(rows))
            check("a table the target does not have is listed",
                  ("table-gone", "x_menu_note_rel", 21, "account.menu_action_invoice_tree1") in by,
                  str(rows))
            check("rows that survived, with or without an xmlid, are left as they are",
                  value(f"SELECT count(*) FROM {hidden} WHERE (menu_id, user_id) IN "
                        "((5, 7), (6, 8))") == "2"
                  and value("SELECT count(*) FROM ir_ui_menu_group_restrict_rel") == "1"
                  and not [r for r in rows if r[3] in ("account.menu_finance", "6")], str(rows))
            check("nothing else was inserted",
                  value(f"SELECT count(*) FROM {hidden}") == "4", "")
            again = _psql(cluster, "probe", menurefs.restore_sql())
            check("a second run inserts nothing",
                  again.returncode == 0
                  and not [r for r in again.stdout.splitlines() if r.startswith("restored")]
                  and "0 put back" in again.stderr, again.stdout + again.stderr)
        finally:
            cluster.stop()

    if failures:
        print("\n".join(["", "FAILED:"] + failures))
        return 1
    print("\nThe menu references keep and restore behave as documented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
