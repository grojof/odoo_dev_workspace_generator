#!/usr/bin/env python3
"""Keep a source's filed declarations and put back what the chain deletes, on a throwaway
PostgreSQL.

The unit suite checks where the driver runs both; this runs their SQL. A source holds two
filed returns, each with boxes linked to journal items and computed with a map. Then what a
later module version does is simulated: it stops shipping the older map, so the update
deletes that map's lines and, through the cascade, the older return's boxes and links. Also
one journal item is gone and a text column became translatable. Checked:

- every box comes back with its id, number and amount; its map line and map come back;
- its links come back, except to the journal item the chain no longer has;
- a box that was never lost is not duplicated, and each box put back is listed;
- the tool's tables are dropped; a box changed by hand makes the check fail and keeps nothing;
- a database without the kept declarations is skipped; a source without them keeps nothing.

    python tools/verify_filed_declarations.py

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

from odoo_dwg import declarations  # noqa: E402

SOURCE = """
    CREATE TABLE account_move_line (id integer PRIMARY KEY, balance numeric);
    CREATE TABLE l10n_es_aeat_map_tax (id serial PRIMARY KEY, model integer NOT NULL,
      date_from date, date_to date);
    CREATE TABLE l10n_es_aeat_map_tax_line (id serial PRIMARY KEY, field_number integer NOT NULL,
      name varchar NOT NULL, map_parent_id integer NOT NULL
        REFERENCES l10n_es_aeat_map_tax(id) ON DELETE RESTRICT);
    CREATE TABLE l10n_es_aeat_tax_line (id serial PRIMARY KEY, res_id integer NOT NULL,
      field_number integer, name varchar, amount numeric, model varchar NOT NULL,
      map_line_id integer NOT NULL REFERENCES l10n_es_aeat_map_tax_line(id) ON DELETE CASCADE);
    CREATE TABLE account_move_line_l10n_es_aeat_tax_line_rel (
      l10n_es_aeat_tax_line_id integer REFERENCES l10n_es_aeat_tax_line(id) ON DELETE CASCADE,
      account_move_line_id integer REFERENCES account_move_line(id) ON DELETE CASCADE,
      PRIMARY KEY (l10n_es_aeat_tax_line_id, account_move_line_id));
    INSERT INTO account_move_line VALUES (1, 100), (2, 50), (3, 21), (4, 200);
    -- An older map (2022) and a current one (2023 on).
    INSERT INTO l10n_es_aeat_map_tax VALUES (1, 303, '2021-07-01', '2022-12-31'), (2, 303, '2023-01-01', NULL);
    INSERT INTO l10n_es_aeat_map_tax_line VALUES (10, 28, 'Base', 1), (11, 29, 'Cuota', 1),
      (20, 28, 'Base', 2), (21, 29, 'Cuota', 2);
    -- A 2022 return (boxes 100, 101) and a 2023 one (boxes 200, 201).
    INSERT INTO l10n_es_aeat_tax_line VALUES (100, 7, 28, 'Base', 150, 'mod303', 10),
      (101, 7, 29, 'Cuota', 31.5, 'mod303', 11), (200, 8, 28, 'Base', 200, 'mod303', 20),
      (201, 8, 29, 'Cuota', 42, 'mod303', 21);
    INSERT INTO account_move_line_l10n_es_aeat_tax_line_rel VALUES (100, 1), (100, 2), (101, 3), (200, 4);
    SELECT setval('l10n_es_aeat_tax_line_id_seq', 300);
    SELECT setval('l10n_es_aeat_map_tax_line_id_seq', 30);
    SELECT setval('l10n_es_aeat_map_tax_id_seq', 3);
"""

# A later module version stops shipping the 2022 map: its update deletes the map's lines (the
# boxes and their links cascade) and the map. One journal item is gone, and the map line's
# name became translatable.
LATER = """
    DELETE FROM l10n_es_aeat_map_tax_line WHERE map_parent_id = 1;
    DELETE FROM l10n_es_aeat_map_tax WHERE id = 1;
    DELETE FROM account_move_line WHERE id = 2;
    ALTER TABLE l10n_es_aeat_map_tax_line ALTER COLUMN name TYPE jsonb USING jsonb_build_object('en_US', name);
"""

BOXES = ("SELECT string_agg(id || ':' || field_number || ':' || amount || ':' || map_line_id, ' ' "
         "ORDER BY id) FROM l10n_es_aeat_tax_line")
LINKS = ("SELECT string_agg(l10n_es_aeat_tax_line_id || '-' || account_move_line_id, ' ' "
         "ORDER BY l10n_es_aeat_tax_line_id, account_move_line_id) "
         "FROM account_move_line_l10n_es_aeat_tax_line_rel")
KEPT_TABLES = (f"SELECT count(*) FROM pg_tables WHERE tablename IN "
               f"({', '.join(repr(k) for _, k in declarations.KEPT)}, '{declarations.KEPT_LINKS}')")


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

    with tempfile.TemporaryDirectory(prefix="odwg-decl-") as tmp:
        cluster = Cluster(Path(tmp), bindir)
        cluster.start()
        try:
            setup(cluster, "probe", SOURCE)
            kept = _psql(cluster, "probe", declarations.keep_sql())
            check("the source's declarations are kept", kept.returncode == 0
                  and "4 boxes, 4 links" in kept.stderr, kept.stderr.strip())
            before = cluster.value(BOXES, "probe")
            later = cluster.sql(LATER, "probe")
            check("a later module version's deletion is simulated", later.returncode == 0
                  and cluster.value("SELECT count(*) FROM l10n_es_aeat_tax_line", "probe") == "2",
                  later.stderr.strip())

            put = _psql(cluster, "probe", declarations.restore_sql(), "-At", "-F", "\t")
            check("putting back runs and commits", put.returncode == 0, put.stderr.strip())
            check("it says what it put back",
                  "2 boxes put back (3 maps and map lines), 2 links put back, 1 links to journal "
                  "items the chain no longer has" in put.stderr, put.stderr.strip())
            check("every box is back with its id, number, amount and map line",
                  cluster.value(BOXES, "probe") == before, cluster.value(BOXES, "probe"))
            check("its map and map line are back, the name as translatable text",
                  cluster.value("SELECT name->>'en_US' || ':' || map_parent_id FROM "
                                "l10n_es_aeat_map_tax_line WHERE id = 10", "probe") == "Base:1"
                  and cluster.value("SELECT count(*) FROM l10n_es_aeat_map_tax WHERE id = 1",
                                    "probe") == "1")
            check("its links are back, except to the journal item the chain no longer has",
                  cluster.value(LINKS, "probe") == "100-1 101-3 200-4", cluster.value(LINKS, "probe"))
            listed = sorted(row.split("\t")[0] for row in put.stdout.splitlines())
            check("each box put back is listed, and only those", listed == ["100", "101"], put.stdout)
            check("the tool's tables are dropped", cluster.value(KEPT_TABLES, "probe") == "0")

            setup(cluster, "edited", SOURCE)
            _psql(cluster, "edited", declarations.keep_sql())
            cluster.sql("UPDATE l10n_es_aeat_tax_line SET amount = 999 WHERE id = 200", "edited")
            boxes = cluster.value(BOXES, "edited")
            edited = _psql(cluster, "edited", declarations.restore_sql(), "-At")
            check("a box that no longer holds its filed amount stops it, and nothing is kept",
                  edited.returncode != 0 and "check failed" in edited.stderr
                  and cluster.value(BOXES, "edited") == boxes
                  and cluster.value(KEPT_TABLES, "edited") == "4", edited.stderr.strip())

            setup(cluster, "stale", SOURCE)
            skipped = _psql(cluster, "stale", declarations.restore_sql(), "-At")
            check("without the kept declarations it skips and says so",
                  skipped.returncode == 0 and "SKIPPED" in skipped.stderr, skipped.stderr.strip())

            setup(cluster, "bare", "CREATE TABLE account_move_line (id integer PRIMARY KEY);")
            bare = _psql(cluster, "bare", declarations.keep_sql())
            check("a source without declarations keeps nothing",
                  bare.returncode == 0 and "the source has none" in bare.stderr
                  and cluster.value(KEPT_TABLES, "bare") == "0", bare.stderr.strip())
        finally:
            cluster.stop()

    if failures:
        print(f"\n{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nFiled declarations are kept and put back as the driver relies on.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
