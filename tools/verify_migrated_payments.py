#!/usr/bin/env python3
"""Repair migrated payments' duplicates and journals, on a throwaway PostgreSQL.

The unit suite checks the SQL's text and where the driver runs it; this runs it on an
18.0-shaped database holding what OCA's 14.0 payment-order migration and OpenUpgrade 18.0 leave:

- a bank payment line with a payment on its order's entry and another on a manual entry: the
  second is removed, with its own links, and listed;
- a duplicate a journal item points at, one with a payment line its twin lacks, one with a
  message: all kept and listed;
- a line whose two payments are both on the order's entry: nothing removed;
- a payment with no journal whose order's bank journal has one method line for its method: given
  that journal and line, its entry untouched; an order on a general journal, or two fitting method
  lines: left and listed;
- a second run changes nothing; a database without payment orders: no error.

Odoo's recompute of states runs in the target's Odoo and is checked on a real migrated database.

    python tools/verify_migrated_payments.py

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

from odoo_dwg import payments  # noqa: E402

SCHEMA = """
    CREATE TABLE account_journal (id integer PRIMARY KEY, type varchar);
    CREATE TABLE account_payment_order (id integer PRIMARY KEY, journal_id integer);
    CREATE TABLE account_move (id integer PRIMARY KEY, name varchar, journal_id integer,
      payment_order_id integer);
    CREATE TABLE account_payment_method_line (id integer PRIMARY KEY, journal_id integer,
      payment_method_id integer);
    CREATE TABLE account_payment (id integer PRIMARY KEY,
      move_id integer REFERENCES account_move ON DELETE SET NULL,
      payment_order_id integer, old_bank_payment_line_id integer, journal_id integer,
      payment_method_id integer, payment_method_line_id integer, state varchar);
    ALTER TABLE account_move ADD COLUMN origin_payment_id integer
      REFERENCES account_payment ON DELETE SET NULL;
    CREATE TABLE account_move_line (id integer PRIMARY KEY, move_id integer,
      payment_id integer REFERENCES account_payment ON DELETE SET NULL);
    CREATE TABLE account_move__account_payment (
      payment_id integer REFERENCES account_payment ON DELETE CASCADE, invoice_id integer);
    CREATE TABLE account_payment_account_payment_line_rel (
      account_payment_id integer REFERENCES account_payment ON DELETE CASCADE,
      account_payment_line_id integer);
    CREATE TABLE mail_message (id serial, model varchar, res_id integer);
    CREATE TABLE mail_followers (id serial, res_model varchar, res_id integer);
    CREATE TABLE ir_attachment (id serial, res_model varchar, res_id integer);
"""

# Journals: 10 bank, 3 general. Orders 1-3 on bank journal 10, order 4 on the general journal.
# Entries 100-103 are the orders' own; 200-204 are manual entries repeating their lines.
DATA = """
    INSERT INTO account_journal VALUES (10, 'bank'), (3, 'general'), (11, 'bank');
    INSERT INTO account_payment_order VALUES (1, 10), (2, 10), (3, 10), (4, 3), (5, 11);
    INSERT INTO account_move (id, name, journal_id, payment_order_id) VALUES
      (100, 'BNK/1', 10, 1), (101, 'BNK/2', 10, 2), (102, 'BNK/3', 10, 3),
      (103, 'MISC/4', 3, 4), (104, 'MISC/5', 3, 5),
      (200, 'MISC/A', 3, NULL), (201, 'MISC/B', 3, NULL), (202, 'MISC/C', 3, NULL),
      (203, 'MISC/D', 3, NULL);
    INSERT INTO account_payment_method_line VALUES (38, 10, 2), (60, 10, 5), (70, 11, 2),
      (71, 11, 2);
    INSERT INTO account_payment (id, move_id, payment_order_id, old_bank_payment_line_id,
      journal_id, payment_method_id, state) VALUES
      -- line 1: kept on the order's entry, a duplicate on a manual entry (removed)
      (1, 100, 1, 1, 10, 2, 'in_process'), (2, 200, 1, 1, NULL, 2, 'in_process'),
      -- line 2: a journal item points at the duplicate (kept)
      (3, 100, 1, 2, 10, 2, 'in_process'), (4, 201, 1, 2, NULL, 2, 'in_process'),
      -- line 3: the duplicate has a payment line its twin lacks (kept)
      (5, 101, 2, 3, 10, 5, 'in_process'), (6, 202, 2, 3, NULL, 5, 'in_process'),
      -- line 4: both on the order's entry (nothing removed)
      (7, 102, 3, 4, 10, 2, 'in_process'), (8, 102, 3, 4, 10, 2, 'in_process'),
      -- line 5: the duplicate has a message (kept)
      (9, 101, 2, 5, 10, 5, 'in_process'), (10, 203, 2, 5, NULL, 5, 'in_process'),
      -- no journal: order 2 on bank journal 10 fits (method 5 -> line 60)
      (11, 101, 2, 6, NULL, 5, 'in_process'),
      -- no journal: order 4 on a general journal, order 5 with two fitting lines
      (12, 103, 4, 7, NULL, 2, 'in_process'), (13, 104, 5, 8, NULL, 2, 'in_process');
    INSERT INTO account_move__account_payment SELECT id, move_id FROM account_payment;
    INSERT INTO account_payment_account_payment_line_rel VALUES (1, 501), (2, 501), (5, 503),
      (6, 503), (6, 504);
    INSERT INTO account_move_line VALUES (900, 201, 4);
    INSERT INTO mail_message (model, res_id) VALUES ('account.payment', 10);
    INSERT INTO mail_followers (res_model, res_id) VALUES ('account.payment', 2);
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

    with tempfile.TemporaryDirectory(prefix="odwg-payments-") as tmp:
        cluster = Cluster(Path(tmp), bindir)
        cluster.start()
        try:
            cluster.sql("CREATE DATABASE probe")
            for part in (SCHEMA, DATA):
                if (done := cluster.sql(part, "probe")).returncode != 0:
                    raise SystemExit(f"fixture failed: {done.stderr.strip()}")
            ran = _psql(cluster, "probe", payments.repair_sql())
            rows = [line.split("\t") for line in ran.stdout.splitlines()]
            by = {(kind, int(pid)): detail for kind, pid, detail in rows}

            def value(sql: str) -> str:
                return cluster.value(sql, "probe")

            check("the SQL runs", ran.returncode == 0, ran.stderr.strip())
            check("a duplicate on a manual entry is removed, with its own links, and listed",
                  ("removed", 2) in by and "kept 1" in by[("removed", 2)]
                  and value("SELECT count(*) FROM account_payment WHERE id = 2") == "0"
                  and value("SELECT count(*) FROM account_move__account_payment "
                            "WHERE payment_id = 2") == "0"
                  and value("SELECT count(*) FROM mail_followers WHERE res_id = 2") == "0",
                  str(rows))
            check("a duplicate a journal item points at is kept, and says why",
                  "account_move_line.payment_id" in by.get(("duplicate-kept", 4), "")
                  and value("SELECT count(*) FROM account_payment WHERE id = 4") == "1",
                  str(rows))
            check("a duplicate with a payment line its twin lacks is kept",
                  by.get(("duplicate-kept", 6)) == "a payment line its twin lacks", str(rows))
            check("a duplicate with a message is kept",
                  by.get(("duplicate-kept", 10)) == "messages or attachments", str(rows))
            check("two payments both on the order's entry are both kept",
                  value("SELECT count(*) FROM account_payment WHERE id IN (7, 8)") == "2"
                  and not any(pid in (7, 8) for _, pid in by), str(rows))
            check("a payment with no journal takes its order's bank journal and method line",
                  value("SELECT journal_id || ':' || payment_method_line_id "
                        "FROM account_payment WHERE id = 11") == "10:60"
                  and ("journal", 11) in by
                  and value("SELECT journal_id || ':' || name FROM account_move "
                            "WHERE id = 101") == "10:BNK/2", str(rows))
            check("a general journal or two fitting method lines give no journal, listed",
                  ("no-journal", 12) in by and ("no-journal", 13) in by
                  and value("SELECT count(*) FROM account_payment WHERE id IN (12, 13) "
                            "AND journal_id IS NULL") == "2", str(rows))
            check("only the one duplicate went",
                  value("SELECT count(*) FROM account_payment") == "12", "")
            again = _psql(cluster, "probe", payments.repair_sql())
            check("a second run removes and assigns nothing",
                  again.returncode == 0
                  and not [r for r in again.stdout.splitlines()
                           if r.split("\t")[0] in ("removed", "journal")],
                  again.stdout + again.stderr)

            cluster.sql("CREATE DATABASE bare")
            cluster.sql("CREATE TABLE account_payment (id integer PRIMARY KEY, journal_id integer,"
                        " payment_method_id integer, payment_method_line_id integer)", "bare")
            bare = _psql(cluster, "bare", payments.repair_sql())
            check("a database without payment orders needs no repair and fails nothing",
                  bare.returncode == 0 and "no payment-order payments" in bare.stderr,
                  bare.stderr.strip())
        finally:
            cluster.stop()

    if failures:
        print("\n".join(["", "FAILED:"] + failures))
        return 1
    print("\nThe payments repair behaves as documented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
