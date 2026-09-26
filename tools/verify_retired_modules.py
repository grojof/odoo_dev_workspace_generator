#!/usr/bin/env python3
"""Retire modules before the chain, as the driver does, on a throwaway PostgreSQL.

The unit suite checks the classification on invented snapshots and where the driver calls
the stage; this runs the stage's own bash (``retire_before_chain``, rendered by
``templates``) with its real ``psql`` snapshots, against a 12.0-shaped registry. Only the
source's Odoo is a stub: it makes the changes an uninstall makes, in SQL.

- the snapshots count rows exactly, with no ANALYZE, and a column's values ignoring
  ``false`` and ``''``;
- an uninstall's differences are named: the registry's tables, a wizard's rows, the
  module's own records, a gone column that was empty, a stored related column;
- a table that lost rows the module did not own, a membership it cascaded to, and a column
  that held values are data lost and stop the stage, naming each;
- the same losses, accepted by name, are listed with their reasons and the stage passes;
- an installed module that depends on a retired one, not retired itself, stops the stage
  before the source's Odoo is ever run.

    python tools/verify_retired_modules.py

Needs PostgreSQL server binaries and bash. No network, no root.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_mail_capture import Cluster, _bindir  # noqa: E402

from odoo_dwg import templates  # noqa: E402
from odoo_dwg.models import MigrationEnv  # noqa: E402

SOURCE, TARGET = "12.0", "18.0"

# The registry as 12.0 holds it, and the client's tables. old_x owns a group, a log, a
# wizard and three fields on others' tables; the partners are many, never analysed.
REGISTRY = """
    CREATE TABLE ir_module_module (id serial PRIMARY KEY, name varchar, state varchar);
    CREATE TABLE ir_module_module_dependency (id serial, module_id integer, name varchar);
    CREATE TABLE ir_model (id serial, model varchar, transient boolean);
    CREATE TABLE ir_model_fields (id integer PRIMARY KEY, model varchar, name varchar,
      store boolean, related varchar);
    CREATE TABLE ir_model_data (id serial, module varchar, model varchar, res_id integer,
      name varchar);
    CREATE TABLE ir_ui_view (id serial, name varchar);
    CREATE TABLE res_groups (id integer PRIMARY KEY, name varchar);
    CREATE TABLE res_groups_users_rel (gid integer, uid integer);
    CREATE TABLE res_partner (id serial, name varchar, old_flag boolean, old_note varchar);
    CREATE TABLE sale_order (id serial, partner_name varchar);
    CREATE TABLE old_log (id serial, name varchar);
    CREATE TABLE old_wizard (id serial);
    INSERT INTO ir_module_module (name, state) VALUES ('base', 'installed'),
      ('old_x', 'installed'), ('sale', 'installed'), ('gone_long_ago', 'uninstalled');
    INSERT INTO ir_module_module_dependency (module_id, name) VALUES (2, 'base'), (3, 'base');
    INSERT INTO ir_model (model, transient) VALUES ('res.partner', false),
      ('old.log', false), ('old.wizard', true);
    INSERT INTO ir_model_fields VALUES (1, 'res.partner', 'name', true, NULL),
      (2, 'res.partner', 'old_flag', true, NULL), (3, 'res.partner', 'old_note', true, NULL),
      (4, 'old.log', 'name', true, NULL), (5, 'sale.order', 'partner_name', true,
      'partner_id.name'), (6, 'res.partner', 'old_computed', false, NULL);
    INSERT INTO ir_model_data (module, model, res_id, name) VALUES
      ('base', 'ir.model.fields', 1, 'field_res_partner__name'),
      ('old_x', 'ir.model.fields', 2, 'field_res_partner__old_flag'),
      ('old_x', 'ir.model.fields', 3, 'field_res_partner__old_note'),
      ('old_x', 'ir.model.fields', 4, 'field_old_log__name'),
      ('old_x', 'ir.model.fields', 5, 'field_sale_order__partner_name'),
      ('old_x', 'ir.model.fields', 6, 'field_res_partner__old_computed'),
      ('old_x', 'res.groups', 2, 'group_old');
    INSERT INTO ir_ui_view (name) SELECT 'v' || n FROM generate_series(1, 10) n;
    INSERT INTO res_groups VALUES (1, 'User'), (2, 'Old feature');
    INSERT INTO res_groups_users_rel VALUES (1, 1), (2, 1), (2, 2);
    INSERT INTO res_partner (name, old_flag, old_note)
      SELECT 'p' || n, false, '' FROM generate_series(1, 5000) n;
    UPDATE res_partner SET old_note = 'kept by hand' WHERE id <= 3;
    INSERT INTO sale_order (partner_name) VALUES ('p1'), ('p2');
    INSERT INTO old_log (name) VALUES ('a'), ('b'), ('c');
    INSERT INTO old_wizard DEFAULT VALUES;
    INSERT INTO old_wizard DEFAULT VALUES;
"""

# What Odoo's uninstall of old_x does to those tables.
UNINSTALL = """
    DELETE FROM res_groups_users_rel WHERE gid = 2;
    DELETE FROM res_groups WHERE id = 2;
    DELETE FROM ir_ui_view WHERE id > 7;
    DELETE FROM ir_model_data WHERE module = 'old_x';
    DROP TABLE old_log;
    DROP TABLE old_wizard;
    ALTER TABLE res_partner DROP COLUMN old_flag, DROP COLUMN old_note;
    ALTER TABLE sale_order DROP COLUMN partner_name;
    UPDATE ir_module_module SET state = 'uninstalled' WHERE name = 'old_x';
"""


def _listing(path: Path) -> dict[str, list[str]]:
    rows = [line.split("\t") for line in path.read_text().splitlines()[1:]]
    return {f"{r[0]}.{r[1]}" if r[1] else r[0]: r[2:] for r in rows}


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

    with tempfile.TemporaryDirectory(prefix="odwg-retire-") as tmp:
        root = Path(tmp)
        cluster = Cluster(root, bindir)
        cluster.start()
        try:
            MigrationEnv.base_dir = str(root / "envs")
            env = MigrationEnv(source=SOURCE, target=TARGET)
            Path(env.logs_dir).mkdir(parents=True)
            odoo = Path(env.source_odoo_bin)
            odoo.parent.mkdir(parents=True)
            odoo.write_text("")
            (root / "uninstall.sql").write_text(UNINSTALL)
            calls = root / "odoo-calls"
            # The source's Odoo shell: the script on stdin must be the uninstall, for the
            # modules the stage passes; the changes are the SQL an uninstall makes.
            python = env.venv_dir(SOURCE) / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text(
                "#!/bin/bash\nbody=$(cat)\n"
                f'echo "$ODWG_RETIRE" >> {calls}\n'
                '[[ "$body" == *button_immediate_uninstall* && "$body" == *ODWG_RETIRE* ]] '
                "|| exit 9\n"
                f"exec psql -X -q -v ON_ERROR_STOP=1 -d \"$DB\" -f {root / 'uninstall.sql'}\n")
            python.chmod(0o755)
            harness = root / "stage.sh"
            harness.write_text("\n".join([
                "set -euo pipefail",
                'die() { echo "[fail] $1" >&2; exit 1; }',
                f'mark() {{ printf "%s\\t%s\\t%s\\n" "$1" "$2" "${{3:-}}" >> {root / "marks"}; }}',
                'neutralise() { echo "[neutralise] $1"; }',
                templates._render_retire_stage(env),
                "retire_before_chain",
                'echo "[done]"', ""]))

            def run(db: str, losses: list[list[str]], extra: str = ""):
                cluster.sql(f"CREATE DATABASE {db}")
                for part in (REGISTRY, extra):
                    if part and (done := cluster.sql(part, db)).returncode != 0:
                        raise SystemExit(f"fixture failed: {done.stderr.strip()}")
                Path(env.decisions_file).write_text(json.dumps({
                    "decisions": [{"module": "old_x", "source": SOURCE, "target": TARGET,
                                   "decision": "dropped", "when": "before-chain"}],
                    "accepted_losses": [{"name": n, "reason": r, "source": SOURCE,
                                         "target": TARGET} for n, r in losses]}))
                calls.unlink(missing_ok=True)
                templates.retired_listing(env).unlink(missing_ok=True)
                return subprocess.run(
                    ["bash", str(harness)], capture_output=True, text=True,
                    env={"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(root), "DB": db,
                         "PGHOST": str(cluster.sock), "PGPORT": str(cluster.port),
                         "PGUSER": "postgres"})

            lost = run("lost", [])
            listing = templates.retired_listing(env)
            rows = _listing(listing) if listing.exists() else {}
            check("the source's Odoo uninstalls the decided module, once",
                  calls.exists() and calls.read_text() == "old_x\n", lost.stderr[-500:])
            check("the registry, a wizard and the module's own group are not data",
                  rows.get("ir_ui_view", [""])[0] == "metadata"
                  and rows.get("old_wizard", [""])[0] == "wizard"
                  and rows.get("res_groups", [""])[:4] == ["module data", "2", "1", "1"],
                  str(rows))
            check("a column never set (false, '') is empty; a stored related one is recomputed",
                  rows.get("res_partner.old_flag", [""])[:2] == ["empty", "0"]
                  and rows.get("sale_order.partner_name", [""])[0] == "recomputed", str(rows))
            before = Path(env.logs_dir) / "00_source-retire" / "rows-before.tsv"
            check("rows are counted exactly: 5000 unanalysed partners, unchanged, not listed",
                  before.exists() and "res_partner\t5000\n" in before.read_text()
                  and "res_partner" not in rows, str(rows))
            check("a table's rows, a cascaded membership and a filled column are data lost",
                  rows.get("old_log", [""])[:3] == ["data lost", "3", "0"]
                  and rows.get("res_groups_users_rel", [""])[:3] == ["data lost", "3", "1"]
                  and rows.get("res_partner.old_note", [""])[:2] == ["data lost", "3"], str(rows))
            check("data lost no one accepted stops the stage, naming each",
                  lost.returncode != 0 and "[done]" not in lost.stdout
                  and all(f"DATA LOST, not accepted: {n}" in lost.stderr for n in
                          ("old_log", "res_groups_users_rel", "res_partner.old_note"))
                  and "retire: data" in (root / "marks").read_text(), lost.stderr[-600:])

            accepted = run("accepted", [["old_log", "the retired feature's log"],
                                        ["res_groups_users_rel", "the retired option's users"],
                                        ["res_partner.old_note", "notes nobody reads"]])
            rows = _listing(listing) if listing.exists() else {}
            check("the same losses, accepted by name, pass with their reasons listed",
                  accepted.returncode == 0 and "[done]" in accepted.stdout
                  and rows.get("old_log", [""])[0] == "accepted"
                  and rows.get("old_log", [""])[-1] == "the retired feature's log"
                  and rows.get("res_partner.old_note", [""])[-1] == "notes nobody reads"
                  and "\tretired\told_x" in (root / "marks").read_text(),
                  accepted.stdout[-600:] + accepted.stderr[-600:])
            check("the snapshots describe the database the chain starts from",
                  cluster.value("SELECT state FROM ir_module_module WHERE name = 'old_x'",
                                "accepted") == "uninstalled"
                  and cluster.value("SELECT to_regclass('old_log') IS NULL", "accepted") == "t",
                  "")

            dependent = run("dependent", [], extra="""
                INSERT INTO ir_module_module (name, state) VALUES ('old_y', 'installed');
                INSERT INTO ir_module_module_dependency (module_id, name)
                  SELECT id, 'old_x' FROM ir_module_module WHERE name = 'old_y';
            """)
            check("an installed dependent not retired stops the stage before Odoo runs",
                  dependent.returncode != 0 and not calls.exists()
                  and "old_y depends on it and is installed" in dependent.stderr
                  and cluster.value("SELECT count(*) FROM old_log", "dependent") == "3",
                  dependent.stderr[-500:])
        finally:
            cluster.stop()

    if failures:
        print("\n".join(["", "FAILED:"] + failures))
        return 1
    print("\nThe retirement before the chain behaves as documented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
