#!/usr/bin/env python3
"""Keep a source's journal-item taxes and take back OpenUpgrade 13.0's additions, on a
throwaway PostgreSQL.

The unit suite checks where the driver runs both; this runs their SQL, on a 12.0-shaped
source that OpenUpgrade 13.0's invoice migration is then simulated on:

- an item grouped in the source (taxes 1 and 2) reused for an invoice line bearing 1 and 3:
  3 is taken back;
- a payable line matched to an invoice line and given its tax: taken back;
- an item that gained a tax its invoice line did not bear: it stays;
- an item whose tax-group children the new model drops: nothing is added back;
- an item OpenUpgrade inserted: never touched;
- each tax taken back is listed, and the tool's tables are dropped;
- a database without the kept taxes: skipped, nothing changed; a source without the
  relation: nothing kept.

    python tools/verify_source_taxes.py

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

from odoo_dwg import sourcetaxes  # noqa: E402

# The source, as 12.0 holds it: journal items and their taxes, invoice lines and theirs.
SOURCE = """
    CREATE TABLE account_move (id integer PRIMARY KEY, name varchar);
    CREATE TABLE account_move_line (id serial PRIMARY KEY, move_id integer, balance numeric);
    CREATE TABLE account_move_line_account_tax_rel (account_move_line_id integer,
      account_tax_id integer, PRIMARY KEY (account_move_line_id, account_tax_id));
    CREATE TABLE account_invoice_line_tax (invoice_line_id integer, tax_id integer);
    INSERT INTO account_move VALUES (1, 'BILL/1'), (2, 'BILL/2');
    INSERT INTO account_move_line (id, move_id, balance) VALUES
      (10, 1, 100), (11, 1, -121), (12, 1, 50), (13, 2, 30), (14, 2, -30);
    -- 10: grouped, taxes 1 and 2. 12: tax 1. 13: a tax group (5) and its children (6, 7).
    INSERT INTO account_move_line_account_tax_rel VALUES (10, 1), (10, 2), (12, 1),
      (13, 5), (13, 6), (13, 7);
    -- Invoice lines 100 (taxes 1, 3), 101 (tax 8), 102 (tax 1), 103 (tax 5), 104 (tax 9).
    INSERT INTO account_invoice_line_tax VALUES (100, 1), (100, 3), (101, 8), (102, 1),
      (103, 5), (104, 9);
    SELECT setval('account_move_line_id_seq', 14);
"""

# What OpenUpgrade 13.0 leaves: items linked to invoice lines, the invoice lines' taxes added,
# an unmatched invoice line inserted, and the tax-group children no longer on the item.
AFTER_13 = """
    ALTER TABLE account_move_line ADD COLUMN old_invoice_line_id integer;
    UPDATE account_move_line SET old_invoice_line_id = 100 WHERE id = 10;
    UPDATE account_move_line SET old_invoice_line_id = 101 WHERE id = 11;
    UPDATE account_move_line SET old_invoice_line_id = 102 WHERE id = 12;
    UPDATE account_move_line SET old_invoice_line_id = 103 WHERE id = 13;
    INSERT INTO account_move_line_account_tax_rel VALUES (10, 3), (11, 8);
    -- A tax the item gained for another reason: its invoice line never bore it.
    INSERT INTO account_move_line_account_tax_rel VALUES (12, 4);
    DELETE FROM account_move_line_account_tax_rel WHERE account_move_line_id = 13
      AND account_tax_id IN (6, 7);
    -- An invoice line OpenUpgrade inserted, with its tax.
    INSERT INTO account_move_line (id, move_id, balance, old_invoice_line_id) VALUES (15, 2, 0, 104);
    INSERT INTO account_move_line_account_tax_rel VALUES (15, 9);
"""

TAXES = ("SELECT string_agg(account_move_line_id || ':' || account_tax_id, ' ' "
         "ORDER BY account_move_line_id, account_tax_id) FROM account_move_line_account_tax_rel")
TABLES = (f"SELECT count(*) FROM pg_tables WHERE tablename IN "
          f"('{sourcetaxes.KEPT_TABLE}', '{sourcetaxes.MAX_ID_TABLE}')")


def _psql(cluster: Cluster, db: str, sql: str, *flags: str) -> subprocess.CompletedProcess[str]:
    """As the driver runs it: ``psql -X -q -v ON_ERROR_STOP=1``, the SQL on stdin."""
    return subprocess.run(
        [str(cluster.bin / "psql"), "-X", "-q", *flags, "-v", "ON_ERROR_STOP=1",
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

    def setup(cluster: Cluster, db: str, *parts: str) -> None:
        cluster.sql(f"CREATE DATABASE {db}")
        for part in parts:
            if (done := cluster.sql(part, db)).returncode != 0:
                raise SystemExit(f"fixture failed: {done.stderr.strip()}")

    with tempfile.TemporaryDirectory(prefix="odwg-srctax-") as tmp:
        cluster = Cluster(Path(tmp), bindir)
        cluster.start()
        try:
            setup(cluster, "probe", SOURCE)
            kept = _psql(cluster, "probe", sourcetaxes.keep_sql())
            check("the source's taxes are kept", kept.returncode == 0
                  and "6 kept" in kept.stderr
                  and cluster.value(f"SELECT id FROM {sourcetaxes.MAX_ID_TABLE}", "probe") == "14",
                  kept.stderr.strip())
            again = _psql(cluster, "probe", sourcetaxes.keep_sql())
            check("keeping again replaces what was kept", again.returncode == 0
                  and cluster.value(f"SELECT count(*) FROM {sourcetaxes.KEPT_TABLE}", "probe") == "6",
                  again.stderr.strip())

            setup_13 = cluster.sql(AFTER_13, "probe")
            check("OpenUpgrade 13.0's additions are simulated", setup_13.returncode == 0,
                  setup_13.stderr.strip())
            taken = _psql(cluster, "probe", sourcetaxes.take_back_sql(), "-At", "-F", "\t")
            check("taking back runs and commits", taken.returncode == 0, taken.stderr.strip())
            check("it says how many it took back",
                  "2 taken back from 2 items" in taken.stderr, taken.stderr.strip())
            after = cluster.value(TAXES, "probe")
            check("an item grouped in the source bears its own taxes again, and a payable line none",
                  after.startswith("10:1 10:2 12:1 12:4"), after)
            check("a tax gained for another reason stays, and dropped children are not added back",
                  "12:4" in after and "13:5" in after and "13:6" not in after, after)
            check("an item OpenUpgrade inserted is not touched", "15:9" in after, after)
            listed = sorted((row.split("\t")[0], row.split("\t")[3]) for row in taken.stdout.splitlines())
            check("each tax taken back is listed", listed == [("10", "3"), ("11", "8")], taken.stdout)
            check("the tool's tables are dropped", cluster.value(TABLES, "probe") == "0")

            setup(cluster, "stale", SOURCE, AFTER_13)
            before = cluster.value(TAXES, "stale")
            skipped = _psql(cluster, "stale", sourcetaxes.take_back_sql(), "-At")
            check("without the kept taxes it skips, says so, and changes nothing",
                  skipped.returncode == 0 and "SKIPPED" in skipped.stderr
                  and cluster.value(TAXES, "stale") == before, skipped.stderr.strip())

            setup(cluster, "bare", "CREATE TABLE account_move_line (id serial PRIMARY KEY);")
            bare = _psql(cluster, "bare", sourcetaxes.keep_sql())
            check("a source without the relation keeps nothing",
                  bare.returncode == 0 and "none to keep" in bare.stderr
                  and cluster.value(TABLES, "bare") == "0", bare.stderr.strip())
        finally:
            cluster.stop()

    if failures:
        print(f"\n{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nThe source's journal-item taxes are kept and the additions taken back as the driver relies on.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
