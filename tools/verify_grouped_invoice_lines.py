#!/usr/bin/env python3
"""Run the repair of grouped invoice items against a throwaway PostgreSQL.

The unit suite checks where the driver runs the repair; this runs its SQL, on
invoices shaped the way OpenUpgrade 13.0 leaves a 12.0 source's grouped items and
16.0 types them:

- a customer invoice: three zero-amount lines under one grouped item, a cent of
  rounding, the grouped item's partner, an analytic line, a declaration link and an
  EC sales list detail on the grouped item;
- a vendor bill whose lines cancel out under two taxes (an import);
- a vendor refund (the other direction);
- a line OpenUpgrade gave the union of its group's taxes;
- a move with one group that adds up and one that does not;
- an open grouped item on a reconcilable account: repaired, its lines open;
- a foreign-currency invoice, a reconciled grouped item, and a grouped item a
  reconciliation points at: left, each with its reason;
- a journal entry marked the same way: never an invoice, never touched;
- a second run, which repairs nothing; a check made to fail, which keeps nothing; a
  database without OpenUpgrade 13.0's columns, and one without grouped items.

    python tools/verify_grouped_invoice_lines.py

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

from odoo_dwg import ungroup  # noqa: E402

SCHEMA = """
    CREATE TABLE res_company (id integer PRIMARY KEY, currency_id integer);
    CREATE TABLE account_account (id integer PRIMARY KEY, code varchar, reconcile boolean);
    CREATE TABLE account_move (id integer PRIMARY KEY, name varchar, move_type varchar,
      company_id integer, currency_id integer, amount_untaxed numeric, amount_tax numeric,
      amount_total numeric, amount_residual numeric);
    CREATE TABLE account_move_line (id serial PRIMARY KEY,
      move_id integer REFERENCES account_move(id) ON DELETE CASCADE, account_id integer,
      partner_id integer, balance numeric, amount_currency numeric, debit numeric,
      credit numeric, price_subtotal numeric, display_type varchar,
      exclude_from_invoice_tab boolean, old_invoice_line_id integer,
      amount_residual numeric DEFAULT 0, amount_residual_currency numeric DEFAULT 0,
      reconciled boolean DEFAULT false);
    CREATE TABLE account_move_line_account_tax_rel (
      account_move_line_id integer REFERENCES account_move_line(id) ON DELETE CASCADE,
      account_tax_id integer, PRIMARY KEY (account_move_line_id, account_tax_id));
    CREATE TABLE account_account_tag_account_move_line_rel (
      account_move_line_id integer REFERENCES account_move_line(id) ON DELETE CASCADE,
      account_account_tag_id integer, PRIMARY KEY (account_move_line_id, account_account_tag_id));
    CREATE TABLE account_invoice_line_tax (invoice_line_id integer, tax_id integer);
    -- OpenUpgrade 13.0's mark: the invoice line it matched to a source journal item.
    CREATE TABLE account_invoice_line (id integer PRIMARY KEY, aml_matched boolean);
    CREATE TABLE account_analytic_line (id serial PRIMARY KEY, amount numeric,
      move_line_id integer REFERENCES account_move_line(id) ON DELETE CASCADE);
    CREATE TABLE account_move_line_l10n_es_aeat_tax_line_rel (
      l10n_es_aeat_tax_line_id integer,
      account_move_line_id integer REFERENCES account_move_line(id) ON DELETE CASCADE,
      PRIMARY KEY (l10n_es_aeat_tax_line_id, account_move_line_id));
    CREATE TABLE l10n_es_aeat_mod349_partner_record_detail (id serial PRIMARY KEY,
      move_line_id integer REFERENCES account_move_line(id) ON DELETE RESTRICT);
    CREATE TABLE account_partial_reconcile (id serial PRIMARY KEY,
      debit_move_id integer REFERENCES account_move_line(id) ON DELETE CASCADE);
    INSERT INTO res_company VALUES (1, 1);
    INSERT INTO account_account VALUES (400, '430000', true), (477, '477000', false),
      (700, '700000', false), (705, '705000', false), (600, '600000', false),
      (410, '410000', true), (472, '472000', false), (555, '555000', true);
"""

# Each invoice: its move, then its lines as (id, account, partner, balance, subtotal,
# excluded, old invoice line, taxes). Balances are signed as the ledger holds them.
FIXTURE = """
    -- 1. A customer invoice: three lines grouped into one item of 100.01 (a cent of rounding).
    INSERT INTO account_move VALUES (1, 'INV/1', 'out_invoice', 1, 1, 100.01, 21, 121.01, 121.01);
    INSERT INTO account_move_line (id, move_id, account_id, partner_id, balance, amount_currency,
        debit, credit, price_subtotal, display_type, exclude_from_invoice_tab, old_invoice_line_id)
      VALUES (101, 1, 400, 7, 121.01, 121.01, 121.01, 0, NULL, 'payment_term', true, NULL),
             (102, 1, 477, 7, -21, -21, 0, 21, NULL, 'tax', true, NULL),
             (103, 1, 700, 7, -100.01, -100.01, 0, 100.01, NULL, 'product', true, NULL),
             (104, 1, 700, 8, 0, 0, 0, 0, 33.33, 'product', false, 1001),
             (105, 1, 700, 8, 0, 0, 0, 0, 33.33, 'product', false, 1002),
             (106, 1, 700, 8, 0, 0, 0, 0, 33.34, 'product', false, 1003);
    INSERT INTO account_move_line_account_tax_rel VALUES (103, 1), (104, 1), (105, 1), (106, 1);
    INSERT INTO account_invoice_line_tax VALUES (1001, 1), (1002, 1), (1003, 1);
    INSERT INTO account_analytic_line (amount, move_line_id) VALUES (100.01, 103);
    INSERT INTO account_move_line_l10n_es_aeat_tax_line_rel VALUES (9, 103);
    INSERT INTO l10n_es_aeat_mod349_partner_record_detail (move_line_id) VALUES (103);

    -- 2. A vendor bill whose lines cancel out under two taxes, grouped per tax.
    INSERT INTO account_move VALUES (2, 'BILL/2', 'in_invoice', 1, 1, 0, 105, 105, 105);
    INSERT INTO account_move_line (id, move_id, account_id, partner_id, balance, amount_currency,
        debit, credit, price_subtotal, display_type, exclude_from_invoice_tab, old_invoice_line_id)
      VALUES (201, 2, 410, 9, -105, -105, 0, 105, NULL, 'payment_term', true, NULL),
             (202, 2, 472, 9, 105, 105, 105, 0, NULL, 'tax', true, NULL),
             (203, 2, 600, 9, 500, 500, 500, 0, NULL, 'product', true, NULL),
             (204, 2, 600, 9, -500, -500, 0, 500, NULL, 'product', true, NULL),
             (205, 2, 600, 9, 0, 0, 0, 0, 500, 'product', false, 2001),
             (206, 2, 600, 9, 0, 0, 0, 0, -500, 'product', false, 2002);
    INSERT INTO account_move_line_account_tax_rel VALUES (203, 12), (204, 124), (205, 12), (206, 124);
    INSERT INTO account_invoice_line_tax VALUES (2001, 12), (2002, 124);

    -- 3. A vendor refund: its lines are credited.
    INSERT INTO account_move VALUES (3, 'RBILL/3', 'in_refund', 1, 1, 80, 0, 80, 80);
    INSERT INTO account_move_line (id, move_id, account_id, partner_id, balance, amount_currency,
        debit, credit, price_subtotal, display_type, exclude_from_invoice_tab, old_invoice_line_id)
      VALUES (301, 3, 410, 9, 80, 80, 80, 0, NULL, 'payment_term', true, NULL),
             (302, 3, 600, 9, -80, -80, 0, 80, NULL, 'product', true, NULL),
             (303, 3, 600, 9, 0, 0, 0, 0, 80, 'product', false, 3001);

    -- 4. A line OpenUpgrade gave the union of its group's taxes (1 and 2); its own was 1.
    INSERT INTO account_move VALUES (4, 'INV/4', 'out_invoice', 1, 1, 40, 0, 40, 40);
    INSERT INTO account_move_line (id, move_id, account_id, partner_id, balance, amount_currency,
        debit, credit, price_subtotal, display_type, exclude_from_invoice_tab, old_invoice_line_id)
      VALUES (401, 4, 400, 7, 40, 40, 40, 0, NULL, 'payment_term', true, NULL),
             (402, 4, 700, 7, -40, -40, 0, 40, NULL, 'product', true, NULL),
             (403, 4, 700, 7, 0, 0, 0, 0, 40, 'product', false, 4001);
    INSERT INTO account_move_line_account_tax_rel VALUES (402, 1), (403, 1), (403, 2);
    INSERT INTO account_invoice_line_tax VALUES (4001, 1);

    -- 5. One group that adds up (700) and one that does not (705): the first is repaired.
    INSERT INTO account_move VALUES (5, 'INV/5', 'out_invoice', 1, 1, 50, 0, 50, 50);
    INSERT INTO account_move_line (id, move_id, account_id, partner_id, balance, amount_currency,
        debit, credit, price_subtotal, display_type, exclude_from_invoice_tab, old_invoice_line_id)
      VALUES (501, 5, 400, 7, 50, 50, 50, 0, NULL, 'payment_term', true, NULL),
             (502, 5, 700, 7, -30, -30, 0, 30, NULL, 'product', true, NULL),
             (503, 5, 700, 7, 0, 0, 0, 0, 30, 'product', false, 5001),
             (504, 5, 705, 7, -20, -20, 0, 20, NULL, 'product', true, NULL),
             (505, 5, 705, 7, 0, 0, 0, 0, 15, 'product', false, 5002);

    -- 6. A foreign-currency invoice.
    INSERT INTO account_move VALUES (6, 'INV/6', 'out_invoice', 1, 2, 10, 0, 10, 10);
    INSERT INTO account_move_line (id, move_id, account_id, partner_id, balance, amount_currency,
        debit, credit, price_subtotal, display_type, exclude_from_invoice_tab, old_invoice_line_id)
      VALUES (601, 6, 400, 7, 10, 12, 10, 0, NULL, 'payment_term', true, NULL),
             (602, 6, 700, 7, -10, -12, 0, 10, NULL, 'product', true, NULL),
             (603, 6, 700, 7, 0, 0, 0, 0, 12, 'product', false, 6001);

    -- 7. A grouped item on a reconcilable account, still open: repaired, and the lines are open.
    INSERT INTO account_move VALUES (7, 'INV/7', 'out_invoice', 1, 1, 10, 0, 10, 10);
    INSERT INTO account_move_line (id, move_id, account_id, partner_id, balance, amount_currency,
        debit, credit, price_subtotal, display_type, exclude_from_invoice_tab, old_invoice_line_id)
      VALUES (701, 7, 400, 7, 10, 10, 10, 0, NULL, 'payment_term', true, NULL),
             (702, 7, 555, 7, -10, -10, 0, 10, NULL, 'product', true, NULL),
             (703, 7, 555, 7, 0, 0, 0, 0, 10, 'product', false, 7001);
    UPDATE account_move_line SET amount_residual = -10, amount_residual_currency = -10 WHERE id = 702;

    -- 8. A grouped item a reconciliation points at.
    INSERT INTO account_move VALUES (8, 'INV/8', 'out_invoice', 1, 1, 10, 0, 10, 10);
    INSERT INTO account_move_line (id, move_id, account_id, partner_id, balance, amount_currency,
        debit, credit, price_subtotal, display_type, exclude_from_invoice_tab, old_invoice_line_id)
      VALUES (801, 8, 400, 7, 10, 10, 10, 0, NULL, 'payment_term', true, NULL),
             (802, 8, 700, 7, -10, -10, 0, 10, NULL, 'product', true, NULL),
             (803, 8, 700, 7, 0, 0, 0, 0, 10, 'product', false, 8001);
    INSERT INTO account_partial_reconcile (debit_move_id) VALUES (802);

    -- 9. A journal entry marked the same way: not an invoice.
    INSERT INTO account_move VALUES (9, 'MISC/9', 'entry', 1, 1, 0, 0, 0, 0);
    INSERT INTO account_move_line (id, move_id, account_id, partner_id, balance, amount_currency,
        debit, credit, price_subtotal, display_type, exclude_from_invoice_tab, old_invoice_line_id)
      VALUES (901, 9, 700, 7, -5, -5, 0, 5, NULL, 'product', true, NULL),
             (902, 9, 400, 7, 5, 5, 5, 0, NULL, 'product', true, NULL);
    -- 10. A grouped item already reconciled.
    INSERT INTO account_move VALUES (10, 'INV/10', 'out_invoice', 1, 1, 10, 0, 10, 10);
    INSERT INTO account_move_line (id, move_id, account_id, partner_id, balance, amount_currency,
        debit, credit, price_subtotal, display_type, exclude_from_invoice_tab, old_invoice_line_id,
        amount_residual, reconciled)
      VALUES (1001, 10, 400, 7, 10, 10, 10, 0, NULL, 'payment_term', true, NULL, 10, false),
             (1002, 10, 555, 7, -10, -10, 0, 10, NULL, 'product', true, NULL, 0, true),
             (1003, 10, 555, 7, 0, 0, 0, 0, 10, 'product', false, 10001, 0, false);
    -- 11. A source item at zero (tax 4, in a declaration box) reused for an invoice line with
    --     another tax: it keeps its zero and its box; its group needed it, so it is left.
    INSERT INTO account_move VALUES (11, 'INV/11', 'out_invoice', 1, 1, 10, 0, 10, 10);
    INSERT INTO account_move_line (id, move_id, account_id, partner_id, balance, amount_currency,
        debit, credit, price_subtotal, display_type, exclude_from_invoice_tab, old_invoice_line_id)
      VALUES (1101, 11, 400, 7, 10, 10, 10, 0, NULL, 'payment_term', true, NULL),
             (1102, 11, 700, 7, -10, -10, 0, 10, NULL, 'product', true, NULL),
             (1103, 11, 700, 7, 0, 0, 0, 0, 1.48, 'product', false, 11001),
             (1104, 11, 700, 7, 0, 0, 0, 0, 8.52, 'product', false, 11002);
    INSERT INTO account_move_line_account_tax_rel VALUES (1102, 1), (1103, 4), (1104, 1);
    INSERT INTO account_invoice_line_tax VALUES (11001, 1), (11002, 1);
    INSERT INTO account_move_line_l10n_es_aeat_tax_line_rel VALUES (28, 1103), (29, 1102);
    INSERT INTO account_invoice_line SELECT DISTINCT old_invoice_line_id, false FROM account_move_line
      WHERE old_invoice_line_id IS NOT NULL;
    UPDATE account_invoice_line SET aml_matched = true WHERE id = 11001;
    SELECT setval('account_move_line_id_seq', 2000);
"""

# Makes the partner check fail: any line whose amount changes loses its partner.
BREAK_PARTNERS = """
    CREATE FUNCTION odwg_break() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.balance IS DISTINCT FROM OLD.balance THEN NEW.partner_id := 999; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER odwg_break BEFORE UPDATE ON account_move_line
      FOR EACH ROW EXECUTE FUNCTION odwg_break();
"""

LINES = ("SELECT string_agg(id || ':' || account_id || ':' || coalesce(partner_id, 0) || ':' "
         "|| balance, ' ' ORDER BY id) FROM account_move_line WHERE move_id = {}")
TAXES = ("SELECT coalesce(string_agg(account_tax_id::text, ',' ORDER BY account_tax_id), '') "
         "FROM account_move_line_account_tax_rel WHERE account_move_line_id = {}")


def _run(cluster: Cluster, db: str) -> tuple[int, str, str]:
    """The repair as the driver runs it: ``psql -X -q -At -F<tab> -v ON_ERROR_STOP=1``, the
    SQL on stdin, the groups left on stdout and the progress on stderr."""
    result = subprocess.run(
        [str(cluster.bin / "psql"), "-X", "-q", "-At", "-F", "\t", "-v", "ON_ERROR_STOP=1",
         "-h", str(cluster.sock), "-p", str(cluster.port), "-U", "postgres", "-d", db, "-w"],
        input=ungroup.ungroup_sql(), capture_output=True, text=True,
    )
    return result.returncode, result.stdout, result.stderr


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

    def setup(cluster: Cluster, db: str, *parts: str) -> None:
        cluster.sql(f"CREATE DATABASE {db}")
        for part in parts:
            if (done := cluster.sql(part, db)).returncode != 0:
                raise SystemExit(f"fixture failed: {done.stderr.strip()}")

    with tempfile.TemporaryDirectory(prefix="odwg-ungroup-") as tmp:
        cluster = Cluster(Path(tmp), bindir)
        cluster.start()
        try:
            setup(cluster, "probe", SCHEMA, FIXTURE)
            code, out, err = _run(cluster, "probe")
            check("the repair runs and commits", code == 0, err.strip())
            check("it says what it repaired",
                  "7 groups repaired on 6 invoices" in err and "5 groups left" in err
                  and "1 reused zero-amount lines kept" in err, err.strip())

            check("a grouped invoice: each line its amount, the cent to the largest, the "
                  "grouped item's partner, the item gone",
                  cluster.value(LINES.format(1), "probe")
                  == "101:400:7:121.01 102:477:7:-21 104:700:7:-33.33 105:700:7:-33.33 "
                     "106:700:7:-33.35",
                  cluster.value(LINES.format(1), "probe"))
            check("its analytic line and EC sales list detail move to the largest line",
                  cluster.value("SELECT move_line_id FROM account_analytic_line", "probe") == "106"
                  and cluster.value("SELECT move_line_id FROM "
                                    "l10n_es_aeat_mod349_partner_record_detail", "probe") == "106")
            check("its declaration link is copied to every line",
                  cluster.value("SELECT string_agg(account_move_line_id::text, ',' ORDER BY 1) "
                                "FROM account_move_line_l10n_es_aeat_tax_line_rel "
                                "WHERE l10n_es_aeat_tax_line_id = 9", "probe")
                  == "104,105,106")
            check("lines that cancel out take their own signed amounts under their own taxes",
                  cluster.value(LINES.format(2), "probe")
                  == "201:410:9:-105 202:472:9:105 205:600:9:500 206:600:9:-500",
                  cluster.value(LINES.format(2), "probe"))
            check("a vendor refund's line is credited",
                  cluster.value(LINES.format(3), "probe") == "301:410:9:80 303:600:9:-80",
                  cluster.value(LINES.format(3), "probe"))
            check("a line given the union of its group's taxes takes back its own",
                  cluster.value(TAXES.format(403), "probe") == "1"
                  and cluster.value(LINES.format(4), "probe") == "401:400:7:40 403:700:7:-40",
                  cluster.value(TAXES.format(403), "probe"))
            check("in a move with an odd group, the group that adds up is repaired and the "
                  "other kept",
                  cluster.value(LINES.format(5), "probe")
                  == "501:400:7:50 503:700:7:-30 504:705:7:-20 505:705:7:0",
                  cluster.value(LINES.format(5), "probe"))
            reasons = {line.split("\t")[1]: line.split("\t")[5] for line in out.splitlines()}
            check("the groups left are listed with their reason",
                  reasons.get("INV/5") == "amounts differ"
                  and reasons.get("INV/6") == "foreign currency"
                  and reasons.get("INV/10") == "reconciled, partly or fully"
                  and reasons.get("INV/11") == "amounts differ"
                  and reasons.get("INV/8") == "referenced by account_partial_reconcile.debit_move_id",
                  out)
            check("a left group is untouched",
                  all(cluster.value(f"SELECT count(*) FROM account_move_line WHERE id = {i}", "probe")
                      == "1" for i in (602, 802, 1002)))
            check("a reused source item at zero keeps its zero, its tax and its declaration box",
                  cluster.value(LINES.format(11), "probe")
                  == "1101:400:7:10 1102:700:7:-10 1103:700:7:0 1104:700:7:0"
                  and cluster.value(TAXES.format(1103), "probe") == "4"
                  and cluster.value("SELECT l10n_es_aeat_tax_line_id FROM "
                                    "account_move_line_l10n_es_aeat_tax_line_rel "
                                    "WHERE account_move_line_id = 1103", "probe") == "28",
                  cluster.value(LINES.format(11), "probe"))
            check("an open grouped item on a reconcilable account leaves its lines open",
                  cluster.value("SELECT balance || ':' || amount_residual FROM account_move_line "
                                "WHERE move_id = 7 AND account_id = 555", "probe") == "-10:-10",
                  cluster.value(LINES.format(7), "probe"))
            check("a journal entry is never touched",
                  cluster.value(LINES.format(9), "probe") == "901:700:7:-5 902:400:7:5")

            code, out2, err = _run(cluster, "probe")
            check("a second run repairs nothing and lists the same groups",
                  code == 0 and "no group can be repaired, 5 left" in err and out2 == out, err.strip())

            # Without OpenUpgrade's mark the reused item would get an amount under a tax its
            # declaration box does not cover: the box's detail would change, and nothing is kept.
            setup(cluster, "unmarked", SCHEMA, FIXTURE,
                  "ALTER TABLE account_invoice_line DROP COLUMN aml_matched;"
                  "UPDATE account_move_line SET price_subtotal = 10 - 1.48 WHERE id = 1104;"
                  "DELETE FROM account_move_line_account_tax_rel WHERE account_move_line_id = 1103;"
                  "INSERT INTO account_move_line_account_tax_rel VALUES (1103, 1);"
                  # The box also holds another invoice's grouped item, as a real box does.
                  "INSERT INTO account_move_line_l10n_es_aeat_tax_line_rel VALUES (28, 103);")
            before = cluster.value(LINES.format(11), "unmarked")
            code, _, err = _run(cluster, "unmarked")
            check("a repair that would change what a declaration box adds up to keeps nothing",
                  code != 0 and "check failed: what a link adds up to changed" in err
                  and cluster.value(LINES.format(11), "unmarked") == before, err.strip())

            setup(cluster, "broken", SCHEMA, FIXTURE, BREAK_PARTNERS)
            before = cluster.value(LINES.format(1), "broken")
            code, _, err = _run(cluster, "broken")
            check("a check that fails stops the repair and names the check",
                  code != 0 and "check failed: a balance per account and partner changed" in err,
                  err.strip())
            check("and keeps nothing of it",
                  cluster.value(LINES.format(1), "broken") == before
                  and cluster.value("SELECT count(*) FROM account_move_line "
                                    "WHERE exclude_from_invoice_tab AND display_type = 'product'",
                                    "broken") == "14")

            setup(cluster, "none", SCHEMA)
            code, out3, err = _run(cluster, "none")
            check("a database without grouped items: nothing to do",
                  code == 0 and "grouped invoice items: none" in err and out3 == "", err.strip())

            setup(cluster, "legacy", "CREATE TABLE account_move_line (id serial PRIMARY KEY);")
            code, out4, err = _run(cluster, "legacy")
            check("a database without OpenUpgrade 13.0's columns: not applicable",
                  code == 0 and "not applicable" in err and out4 == "", err.strip())
        finally:
            cluster.stop()

    if failures:
        print(f"\n{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nThe repair of grouped invoice items behaves as the driver relies on.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
