#!/usr/bin/env python3
"""Run ``migrate audit`` against a throwaway PostgreSQL, on databases shaped like 12.0 and 18.0.

The unit suite checks the verdicts on invented rows; this runs every query for real:

- a 12.0-shaped copy: two journals sharing a code and two differing by case, a bank day
  imported twice, an unreconciled line matching a payment posted on the bank account, and
  an unreconciled line of a closed period;
- an 18.0-shaped database: a declared unique constraint PostgreSQL does not have, one whose
  name PostgreSQL truncated, a foreign key and an uninstalled module's constraint (neither
  read), a required many2one empty on an active record, a required field empty only on
  archived ones, a required binary without its attachment, a transient model (not read),
  and a statement line stored as reconciled with a line still in suspense;
- the same database read by a role refused one table: that check unreadable, the others
  standing.

    python tools/verify_migration_audit.py

Needs PostgreSQL server binaries. No network, no root.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_mail_capture import Cluster, _bindir  # noqa: E402

from odoo_dwg import cli  # noqa: E402

_IR = """
    CREATE TABLE ir_model (id serial, model varchar, transient boolean);
    CREATE TABLE ir_model_fields (id serial, model varchar, name varchar, ttype varchar,
                                  required boolean, store boolean);
    CREATE TABLE ir_module_module (id serial, name varchar, state varchar);
    CREATE TABLE ir_model_constraint (id serial, name varchar, definition varchar, type varchar,
                                      model int, module int);
    CREATE TABLE ir_attachment (id serial, res_model varchar, res_field varchar, res_id int);
"""

V12_DB = _IR + """
    CREATE TABLE res_company (id int, fiscalyear_lock_date date, period_lock_date date);
    CREATE TABLE account_account (id int, internal_type varchar);
    CREATE TABLE account_journal (id int, company_id int, code varchar, name varchar,
        type varchar, active boolean, default_debit_account_id int, default_credit_account_id int);
    CREATE TABLE account_move (id int, journal_id int, date date, state varchar);
    CREATE TABLE account_bank_statement (id int, journal_id int, company_id int,
                                         balance_start numeric, balance_end_real numeric);
    CREATE TABLE account_bank_statement_line (id int, statement_id int, journal_id int, date date,
        amount numeric, name varchar, ref varchar, note text, partner_name varchar, partner_id int);
    CREATE TABLE account_move_line (id serial, move_id int, journal_id int, account_id int,
        statement_line_id int, payment_id int, balance numeric, partner_id int,
        reconciled boolean DEFAULT true, amount_residual numeric DEFAULT 0);
    INSERT INTO res_company VALUES (1, '2025-03-03', NULL);
    INSERT INTO account_account VALUES (1, 'receivable'), (2, 'liquidity');
    INSERT INTO account_journal VALUES (1, 1, 'BANK1', 'Bank A', 'bank', true, 2, 2),
        (2, 1, 'BANK1', 'Bank B', 'bank', true, 2, 2), (3, 1, 'CSH1', 'Cash A', 'cash', true, 2, 2),
        (4, 1, 'csh1', 'Cash B', 'cash', true, 2, 2);
    -- 5 March imported twice (statements 1 and 2); a payment of 250 posted on the bank and its
    -- line unreconciled (3); a line of a closed period (4).
    INSERT INTO account_bank_statement VALUES (1, 1, 1, 100, 150), (2, 1, 1, 100, 150),
        (3, 1, 1, 150, 400), (4, 1, 1, 0, -9.50);
    INSERT INTO account_bank_statement_line VALUES
        (1, 1, 1, '2025-03-05', 50, 'transfer', NULL, NULL, NULL, NULL),
        (2, 2, 1, '2025-03-05', 50, 'transfer', NULL, NULL, NULL, NULL),
        (3, 3, 1, '2025-03-10', 250, 'customer', NULL, NULL, NULL, NULL),
        (4, 4, 1, '2025-01-02', -9.50, 'fee', NULL, NULL, NULL, NULL);
    INSERT INTO account_move VALUES (1, 1, '2025-03-09', 'posted');
    INSERT INTO account_move_line (move_id, journal_id, account_id, payment_id, balance)
        VALUES (1, 1, 2, 1, 250), (1, 1, 1, 1, -250);
    INSERT INTO ir_model (model, transient) VALUES ('account.journal', false);
    INSERT INTO ir_model_fields (model, name, ttype, required, store)
        VALUES ('account.journal', 'code', 'char', true, true);
"""

LONG_NAME = "acme_thing_" + "a_rather_long_constraint_name_" * 2  # 71 characters

V18_DB = _IR + f"""
    CREATE TABLE account_journal (id int, company_id int, code varchar, name varchar,
        type varchar, active boolean, suspense_account_id int,
        CONSTRAINT account_journal_code_company_uniq UNIQUE (company_id, code));
    CREATE TABLE account_move (id int, journal_id int, date date);
    CREATE TABLE account_move_line (id serial, move_id int, account_id int,
                                    statement_line_id int, payment_id int);
    CREATE TABLE account_bank_statement_line (id int, move_id int, is_reconciled boolean);
    INSERT INTO account_journal VALUES (1, 1, 'BANK1', 'Bank', 'bank', true, 9);
    INSERT INTO account_move VALUES (1, 1, '2025-03-05'), (2, 1, '2025-03-06'), (3, 1, '2025-03-07');
    INSERT INTO account_move_line (move_id, account_id) VALUES (1, 9), (1, 2), (2, 2), (3, 9);
    INSERT INTO account_bank_statement_line VALUES (1, 1, true), (2, 2, true), (3, 3, false);

    CREATE TABLE acme_thing (id int, name varchar NOT NULL, partner_id int, active boolean,
                             CONSTRAINT "{LONG_NAME}" CHECK (id > 0));
    CREATE TABLE acme_type (id int, location_id int, active boolean);
    CREATE TABLE acme_certificate (id int);
    CREATE TABLE acme_wizard (id int, x int);
    INSERT INTO acme_thing VALUES (1, 'a', 7, true), (2, 'b', NULL, true);
    INSERT INTO acme_type VALUES (1, 3, true), (2, NULL, false);
    INSERT INTO acme_certificate VALUES (1), (2);
    INSERT INTO acme_wizard VALUES (1, NULL);
    INSERT INTO ir_attachment (res_model, res_field, res_id) VALUES ('acme.certificate', 'file', 1);
    INSERT INTO ir_model (model, transient) VALUES ('acme.thing', false), ('acme.type', false),
        ('acme.certificate', false), ('acme.wizard', true), ('account.journal', false);
    INSERT INTO ir_model_fields (model, name, ttype, required, store) VALUES
        ('acme.thing', 'name', 'char', true, true), ('acme.thing', 'partner_id', 'many2one', true, true),
        ('acme.type', 'location_id', 'many2one', true, true),
        ('acme.certificate', 'file', 'binary', true, true), ('acme.wizard', 'x', 'integer', true, true);
    INSERT INTO ir_module_module (name, state) VALUES ('acme', 'installed'), ('old', 'uninstalled');
    INSERT INTO ir_model_constraint (name, definition, type, model, module) VALUES
        ('acme_thing_name_uniq', 'unique(name)', 'u', 1, 1),
        ('{LONG_NAME}', 'CHECK(id > 0)', 'u', 1, 1),
        ('acme_thing_partner_id_fkey', '', 'f', 1, 1),
        ('acme_type_gone_uniq', 'unique(x)', 'u', 2, 2),
        ('account_journal_code_company_uniq', 'unique(company_id,code)', 'u', 5, 1);
    ALTER TABLE ir_model_fields ADD COLUMN relation varchar;
    INSERT INTO ir_model_fields (model, name, ttype, relation) VALUES
        ('sale.order', 'name', 'char', NULL), ('sale.order', 'state', 'selection', NULL),
        ('sale.order', 'date_order', 'datetime', NULL),
        ('sale.order', 'partner_id', 'many2one', 'res.partner'),
        ('res.partner', 'name', 'char', NULL);
    CREATE TABLE ir_filters (id int, model_id varchar, domain text, context text, sort text);
    INSERT INTO ir_filters VALUES
        (1, 'sale.order', E'[("partner_id.name", "ilike", "a"),\n\t("date_order", ">=", '
            '(context_today() - relativedelta(days=7)).strftime("%Y-%m-%d"))]',
            '{{''group_by'': [''date_order:month'']}}', '["-date_order", "name desc"]'),
        (2, 'sale.order', '[("pnt_state", "=", "x"), ("state", "in", ["a", "in", "b"])]',
            '{{''orderedBy'': [{{''name'': ''amount'', ''asc'': True}}]}}', '[]'),
        (3, 'stock.inventory', '[]', '{{}}', '[]'),
        (4, 'sale.order', '[("name", "=", ', '{{}}', '[]');
    CREATE TABLE ir_exports (id int, resource varchar);
    CREATE TABLE ir_exports_line (id int, export_id int, name varchar);
    INSERT INTO ir_exports VALUES (1, 'sale.order');
    INSERT INTO ir_exports_line VALUES (1, 1, 'partner_id/name'), (2, 1, 'partner_id/.id'),
        (3, 1, '.id'), (4, 1, 'invoice_ids/date_invoice');
    CREATE ROLE reader LOGIN;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO reader;
    REVOKE SELECT ON ir_model_constraint FROM reader;
"""


def _audit(cluster: Cluster, db: str, user: str = "postgres") -> tuple[int, str]:
    out = io.StringIO()
    # The checks read plain text: a terminal's FORCE_COLOR would put escapes inside it.
    os.environ["NO_COLOR"] = "1"
    with contextlib.redirect_stdout(out):
        code = cli.main(["migrate", "audit", "--database", db, "--db-host", str(cluster.sock),
                         "--db-port", str(cluster.port), "--db-user", user, "--lang", "en"])
    return code, out.getvalue()


def main() -> int:
    bindir = _bindir()
    if bindir is None:
        print("No PostgreSQL server binaries found under /usr/lib/postgresql.")
        return 1
    failures: list[str] = []

    def check(label: str, condition: bool, detail: object = "") -> None:
        print(f"{'ok  ' if condition else 'FAIL'}  {label}")
        if not condition:
            failures.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory(prefix="odwg-audit-") as tmp:
        cluster = Cluster(Path(tmp), bindir)
        cluster.start()
        try:
            cluster.sql("CREATE DATABASE a12")
            cluster.value(V12_DB + " SELECT 1", "a12")
            code, out = _audit(cluster, "a12")
            check("12.0: exit 1", code == 1, out)
            check("12.0: the shared code, and the case-only one as information",
                  "company 1: BANK1 (shared, journals 1, 2)" in out
                  and "company 1: CSH1 (confusable, journals 3, 4)" in out, out)
            check("12.0: the day imported twice", "line 2 (journal BANK1, 2025-03-05, 50): "
                  "duplicate of 1" in out, out)
            check("12.0: the line matching a payment on the bank, open period",
                  "line 3 (journal BANK1, 2025-03-10, 250)" in out
                  and "closed periods: 0, open periods: 1" in out, out)
            check("12.0: the closed-period line, as information",
                  "[INFO] Unreconciled bank lines of closed periods: 1" in out
                  and "line 4 (journal BANK1, 2025-01-02, -9.50)" in out, out)
            check("12.0: constraints and required fields clean",
                  "Declared constraints PostgreSQL does not have: none" in out
                  and "Required fields left empty: none" in out, out)
            check("12.0: the reconciled flag is not applicable",
                  "suspense: not applicable to this database" in out, out)

            cluster.sql("CREATE DATABASE a18")
            cluster.value(V18_DB + " SELECT 1", "a18")
            code, out = _audit(cluster, "a18")
            check("18.0: exit 1", code == 1, out)
            check("18.0: the bank checks of sources up to 13.0 are not applicable",
                  out.count("not applicable to this database") == 3, out)
            check("18.0: the journal constraint holds, so no code is reported",
                  "Journal codes shared within a company: none" in out, out)
            check("18.0: only the missing unique constraint (not the truncated, the foreign key "
                  "or the uninstalled module's)",
                  "Declared constraints PostgreSQL does not have: 1" in out
                  and "acme.thing: acme_thing_name_uniq unique(name) (acme)" in out
                  and "rather_long" not in out and "fkey" not in out
                  and "acme_type_gone_uniq" not in out, out)
            check("18.0: the empty required fields, the archived-only one as information",
                  "acme.certificate.file: 1 empty, 1 active" in out
                  and "acme.thing.partner_id: 1 empty, 1 active" in out
                  and "acme.type.location_id: 1 empty, archived only" in out
                  and "acme.thing.name" not in out and "acme.wizard" not in out, out)
            check("18.0: saved filters and exports naming fields the database lacks, and only them",
                  "naming fields the database lacks: 4" in out
                  and "filter 2 on sale.order: pnt_state, amount" in out
                  and "filter 3 on stock.inventory: model stock.inventory is gone" in out
                  and "filter 4 on sale.order: its domain does not parse" in out
                  and "export 1 on sale.order: invoice_ids/date_invoice" in out
                  and "3 filters, 1 exports" in out and "filter 1 " not in out, out)
            check("18.0: the line stored as reconciled with a suspense line, and only it",
                  "suspense: 1" in out and "line 1 (journal BANK1, 2025-03-05)" in out, out)

            code, out = _audit(cluster, "a18", "reader")
            check("a role refused one table: that check unreadable, the others standing",
                  code == 1 and "Declared constraints PostgreSQL does not have: could not be "
                  "read" in out and "acme.certificate.file: 1 empty" in out, out)

            code, out = _audit(cluster, "postgres")
            check("a database that is not Odoo: exit 2", code == 2
                  and "is not an Odoo database" in out, out)
        finally:
            cluster.stop()

    if failures:
        print(f"\n{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
