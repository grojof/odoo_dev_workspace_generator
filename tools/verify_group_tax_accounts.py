#!/usr/bin/env python3
"""The accounts of former group taxes, set after the 13.0 step, on a throwaway PostgreSQL.

The unit suite checks where the driver runs it; this runs its SQL on a 13.0-shaped database as
OpenUpgrade 13.0 leaves a localisation's group taxes:

- a group with a positive and a negative child: each tax line takes the account of the child of
  its sign, for invoices and for refunds, and each line written is listed;
- a child with an account of the company's own: that account, not a standard one;
- a line that already has an account keeps it;
- a base line is never written, and a child without account gives none;
- a tax that was never a group is not touched;
- a second run writes nothing.

    python tools/verify_group_tax_accounts.py

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

from odoo_dwg import grouptaxes  # noqa: E402

# Taxes 10 and 20 were groups (children 11/12 and 21/22); 30 never was. Repartition lines as
# OpenUpgrade 13.0 creates them: the children's with their accounts, the groups' without.
FIXTURE = """
    CREATE TABLE account_account (id integer PRIMARY KEY, code varchar);
    CREATE TABLE account_tax (id integer PRIMARY KEY, name varchar, amount numeric);
    CREATE TABLE account_tax_filiation_rel (parent_tax integer, child_tax integer);
    CREATE TABLE account_tax_repartition_line (id serial PRIMARY KEY, invoice_tax_id integer,
      refund_tax_id integer, repartition_type varchar, factor_percent float, account_id integer);
    INSERT INTO account_account VALUES (472, '472000'), (477, '477000'), (4721, '472001'),
      (600, '600000');
    INSERT INTO account_tax VALUES (10, 'Intra-EU 21%', 21), (11, 'Intra-EU 21% (1)', 21),
      (12, 'Intra-EU 21% (2)', -21), (20, 'Reverse charge 10%', 10),
      (21, 'Reverse charge 10% (1)', -10), (22, 'Reverse charge 10% (2)', 10),
      (30, 'VAT 21%', 21);
    INSERT INTO account_tax_filiation_rel VALUES (10, 11), (10, 12), (20, 21), (20, 22);
    INSERT INTO account_tax_repartition_line
        (id, invoice_tax_id, refund_tax_id, repartition_type, factor_percent, account_id) VALUES
      -- Group 10: no account anywhere.
      (1, 10, NULL, 'base', 100, NULL), (2, 10, NULL, 'tax', 100, NULL),
      (3, 10, NULL, 'tax', -100, NULL), (4, NULL, 10, 'base', 100, NULL),
      (5, NULL, 10, 'tax', 100, NULL), (6, NULL, 10, 'tax', -100, NULL),
      -- Its children: the company's own account on the deductible side; refunds on 472.
      (7, 11, NULL, 'base', 100, NULL), (8, 11, NULL, 'tax', 100, 4721),
      (9, NULL, 11, 'base', 100, NULL), (10, NULL, 11, 'tax', 100, 472),
      (11, 12, NULL, 'base', 100, NULL), (12, 12, NULL, 'tax', 100, 477),
      (13, NULL, 12, 'base', 100, NULL), (14, NULL, 12, 'tax', 100, 477),
      -- Group 20: one line already has an account; the negative child has none on refunds.
      (15, 20, NULL, 'tax', 100, 600), (16, 20, NULL, 'tax', -100, NULL),
      (17, NULL, 20, 'tax', 100, NULL), (18, NULL, 20, 'tax', -100, NULL),
      (19, 21, NULL, 'tax', 100, 477), (20, NULL, 21, 'tax', 100, NULL),
      (21, 22, NULL, 'tax', 100, 472), (22, NULL, 22, 'tax', 100, 472),
      -- Never a group.
      (23, 30, NULL, 'tax', 100, NULL);
    SELECT setval('account_tax_repartition_line_id_seq', 100);
"""

ACCOUNTS = ("SELECT string_agg(l.id || ':' || coalesce(a.code, '-'), ' ' ORDER BY l.id) "
            "FROM account_tax_repartition_line l LEFT JOIN account_account a ON a.id = l.account_id "
            "WHERE l.id IN ({})")


def _repair(cluster: Cluster, db: str) -> subprocess.CompletedProcess[str]:
    """As the driver runs it: ``psql -X -q -At -F<tab> -v ON_ERROR_STOP=1``, the SQL on stdin."""
    return subprocess.run(
        [str(cluster.bin / "psql"), "-X", "-q", "-At", "-F", "\t", "-v", "ON_ERROR_STOP=1",
         "-h", str(cluster.sock), "-p", str(cluster.port), "-U", "postgres", "-d", db, "-w"],
        input=grouptaxes.repair_sql(), capture_output=True, text=True,
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

    with tempfile.TemporaryDirectory(prefix="odwg-grouptax-") as tmp:
        cluster = Cluster(Path(tmp), bindir)
        cluster.start()
        try:
            cluster.sql("CREATE DATABASE probe")
            if (done := cluster.sql(FIXTURE, "probe")).returncode != 0:
                raise SystemExit(f"fixture failed: {done.stderr.strip()}")
            done = _repair(cluster, "probe")
            check("the repair runs", done.returncode == 0, done.stderr.strip())
            group_10 = cluster.value(ACCOUNTS.format("1,2,3,4,5,6"), "probe")
            check("each tax line takes the account of the child of its sign, per document; "
                  "the company's own account is kept; base lines are not written",
                  group_10 == "1:- 2:472001 3:477000 4:- 5:472000 6:477000", group_10)
            group_20 = cluster.value(ACCOUNTS.format("15,16,17,18"), "probe")
            check("a line with an account keeps it, and a child without account gives none",
                  group_20 == "15:600000 16:477000 17:472000 18:-", group_20)
            check("a tax that was never a group is not touched",
                  cluster.value(ACCOUNTS.format("23"), "probe") == "23:-")
            rows = [line.split("\t") for line in done.stdout.splitlines()]
            check("each line written is listed: tax, document, factor and account",
                  len(rows) == 6
                  and ["10", "Intra-EU 21%", "invoice", "100", "472001"] in rows
                  and ["10", "Intra-EU 21%", "refund", "-100", "477000"] in rows
                  and ["20", "Reverse charge 10%", "refund", "100", "472000"] in rows,
                  done.stdout)
            again = _repair(cluster, "probe")
            check("a second run writes nothing",
                  again.returncode == 0 and again.stdout == ""
                  and cluster.value(ACCOUNTS.format("1,2,3,4,5,6"), "probe") == group_10,
                  again.stdout)
        finally:
            cluster.stop()

    if failures:
        print(f"\n{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nThe former group taxes get their children's accounts as the driver relies on.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
