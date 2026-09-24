#!/usr/bin/env python3
"""Execute what taking in a client copy relies on, against throwaway instances.

The unit suite classifies invented text; this produces the real thing:

- a real ``pg_restore`` stderr, with one error of a known class (an aggregate on
  ``array_cat``) and one of no class, read and classified;
- the generated restore plan, run: the reference is created and restored, the
  errors kept in their file;
- the generated reader-role plan, run (with a ``sudo`` that stands in for the
  superuser): the password never in the command, written to ``.pgpass`` mode 600,
  the role able to log in with it, refused secrets and writes;
- a git history with a merge whose resolution is a version no other commit has:
  ``git_raw_log`` finds it, the core is identified, and the exact commit is the
  merge; ``git_blob_id`` agrees with ``git hash-object``;
- the generated filestore plan, run on an archive with an extra top level.

    python tools/verify_intake.py

Needs PostgreSQL server binaries, ``git`` and ``tar``. No network, no root.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_mail_capture import Cluster, _bindir  # noqa: E402

from odoo_dwg import intake, planners, system  # noqa: E402
from odoo_dwg.models import MigrationEnv  # noqa: E402

SOURCE_DB = """
    CREATE FUNCTION public.array_cat(anyarray, anyarray) RETURNS anyarray
      LANGUAGE sql IMMUTABLE AS 'SELECT $1 || $2';
    CREATE AGGREGATE public.array_concat_agg(anyarray) (SFUNC = public.array_cat, STYPE = anyarray);
    CREATE TYPE public.mood AS ENUM ('ok', 'sad');
    CREATE TABLE public.feelings (id serial PRIMARY KEY, m public.mood);
    CREATE TABLE res_users (id serial PRIMARY KEY, login varchar, password varchar);
    CREATE TABLE ir_config_parameter (id serial PRIMARY KEY, key varchar, value text);
    CREATE TABLE res_partner (id serial PRIMARY KEY, name varchar);
    INSERT INTO res_users (login, password) VALUES ('admin', 'hash');
    INSERT INTO ir_config_parameter (key, value) VALUES ('database.secret', 's3cret');
    INSERT INTO res_partner (name) VALUES ('ACME');
"""

# The audit's fixture: a client module "acme" with a field on partners, a model of its own,
# a wizard opened twice, a dependent, and a document registered under "account".
AUDIT_DB = """
    CREATE TABLE ir_model (id serial, model varchar, transient boolean);
    CREATE TABLE ir_model_data (id serial, module varchar, name varchar, model varchar, res_id int);
    CREATE TABLE ir_model_fields (id serial, model varchar, name varchar, ttype varchar,
                                  store boolean, related varchar, relation_table varchar);
    CREATE TABLE ir_module_module (id serial, name varchar, state varchar);
    CREATE TABLE ir_module_module_dependency (id serial, module_id int, name varchar);
    CREATE TABLE ir_act_report_xml (id serial, report_name varchar, model varchar,
                                    binding_model_id int, print_report_name varchar);
    CREATE TABLE ir_attachment (id serial, name varchar, create_date timestamp);
    CREATE TABLE res_partner (id serial, acme_flag boolean, acme_note varchar,
                              write_date timestamp);
    CREATE TABLE acme_thing (id serial, name varchar, write_date timestamp);
    CREATE SEQUENCE acme_wizard_id_seq;
    SELECT nextval('acme_wizard_id_seq'); SELECT nextval('acme_wizard_id_seq');
    INSERT INTO ir_model (model, transient) VALUES ('acme.thing', false), ('acme.wizard', true);
    INSERT INTO ir_model_data (module, name, model, res_id) VALUES
        ('acme', 'model_acme_thing', 'ir.model', 1), ('acme', 'model_acme_wizard', 'ir.model', 2),
        ('acme', 'f1', 'ir.model.fields', 1), ('acme', 'f2', 'ir.model.fields', 2),
        ('account', 'report_acme_invoice', 'ir.actions.report', 1);
    INSERT INTO ir_model_fields (model, name, ttype, store) VALUES
        ('res.partner', 'acme_flag', 'boolean', true), ('res.partner', 'acme_note', 'char', true);
    INSERT INTO res_partner (acme_flag, acme_note, write_date) VALUES
        (true, 'x', '2026-02-01'), (false, '', '2026-02-01'), (true, NULL, '2023-05-01');
    INSERT INTO acme_thing (name, write_date) VALUES ('a', '2022-01-01');
    INSERT INTO ir_module_module (name, state) VALUES ('acme', 'installed'),
        ('acme_extra', 'installed');
    INSERT INTO ir_module_module_dependency (module_id, name) VALUES (2, 'acme');
    INSERT INTO ir_act_report_xml (report_name, model, binding_model_id, print_report_name)
        VALUES ('acme.invoice', 'account.invoice', 7, $$'ACME invoice - %s' % (object.name)$$);
    INSERT INTO ir_attachment (name, create_date) VALUES
        ('ACME invoice - INV1.pdf', '2026-03-01'), ('ACME invoice - INV0.pdf', '2021-01-01');
"""

# Bank statements for the duplicates step. Journal 1: statement 1 and 2 match their files
# and both hold 3 March with the same lines and the same end-of-day balance (157). Two equal
# fees in one day are two movements. Fee 1 is reconciled in both copies; the +50 only in
# statement 1. Statement 3 repeats 4 March but does not match its file, so it proves nothing.
BANK_DB = """
    CREATE TABLE res_company (id int, fiscalyear_lock_date date, period_lock_date date);
    CREATE TABLE account_journal (id int, code varchar);
    CREATE TABLE account_bank_statement (id int, journal_id int, company_id int,
                                         balance_start numeric, balance_end_real numeric);
    CREATE TABLE account_bank_statement_line (id int, statement_id int, journal_id int, date date,
        amount numeric, name varchar, ref varchar, note text, partner_name varchar);
    CREATE TABLE account_move_line (id serial, statement_line_id int);
    INSERT INTO res_company VALUES (1, '2025-03-03', NULL);
    INSERT INTO account_journal VALUES (1, 'BNK1');
    INSERT INTO account_bank_statement VALUES (1, 1, 1, 100, 157), (2, 1, 1, 110, 162),
                                              (3, 1, 1, 157, 999);
    INSERT INTO account_bank_statement_line VALUES
        (1, 1, 1, '2025-03-01', 10, 'transfer', NULL, NULL, 'ACME'),
        (2, 1, 1, '2025-03-03', -1.50, 'fee', NULL, NULL, NULL),
        (3, 1, 1, '2025-03-03', -1.50, 'fee', NULL, NULL, NULL),
        (4, 1, 1, '2025-03-03', 50, 'payment', 'R1', NULL, 'ACME'),
        (5, 2, 1, '2025-03-03', -1.50, 'fee', NULL, NULL, NULL),
        (6, 2, 1, '2025-03-03', -1.50, 'fee', NULL, NULL, NULL),
        (7, 2, 1, '2025-03-03', 50, 'payment', 'R1', NULL, 'ACME'),
        (8, 2, 1, '2025-03-04', 5, 'interest', NULL, NULL, NULL),
        (9, 3, 1, '2025-03-04', 5, 'interest', NULL, NULL, NULL);
    INSERT INTO account_move_line (statement_line_id) VALUES (2), (4), (5);
"""


def _bash(command: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", command], capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


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

    with tempfile.TemporaryDirectory(prefix="odwg-intake-") as tmp:
        root = Path(tmp)
        cluster = Cluster(root, bindir)
        cluster.start()
        pg = {"PATH": f"{bindir}:{os.environ['PATH']}", "PGHOST": str(cluster.sock),
              "PGPORT": str(cluster.port), "PGUSER": "postgres"}
        try:
            # --- a real pg_restore stderr -----------------------------------------------
            cluster.sql("CREATE DATABASE src")
            cluster.value(SOURCE_DB + " SELECT 1", "src")
            dump = root / "client.dump"
            _bash(f"pg_dump -Fc -f {dump} src", pg)
            listing = _bash(f"pg_restore -l {dump}", pg).stdout
            # What a PostgreSQL 14+ server cannot recreate, and what a lost type does.
            kept = "\n".join(line for line in listing.splitlines()
                             if " FUNCTION public array_cat" not in line
                             and " TYPE public mood" not in line)
            (root / "toc.list").write_text(kept)
            cluster.sql("CREATE DATABASE partial")
            restored = _bash(f"pg_restore --no-owner --no-acl -L {root / 'toc.list'} "
                             f"-d partial {dump}", pg)
            verdicts = intake.classify(intake.parse_restore_errors(restored.stderr))
            known = [v for v in verdicts if v[1] is not None]
            unknown = [v for v in verdicts if v[1] is None]
            # A lost type is not one error but a cascade: the table, its sequence, its
            # default, its data and its key each fail after it. None of them is known.
            check("a real pg_restore stderr: the aggregate is the known class, the type is not",
                  len(known) == 1 and known[0][1] is not None
                  and known[0][1].id == "array-cat-anyarray-aggregate"
                  and len(unknown) >= 1 and all("mood" in e.message or "feelings" in e.message
                                                for e, _ in unknown),
                  restored.stderr)

            # --- the restore plan, run ----------------------------------------------------
            MigrationEnv.base_dir = str(root / "envs")
            env = MigrationEnv(source="12.0", target="18.0", db_host=str(cluster.sock),
                               db_port=cluster.port, db_user="postgres")
            for command in planners.plan_intake_restore(env, dump, "ACME_original"):
                run = _bash(command.command, pg)
                check(f"restore plan: {command.description}", run.returncode == 0, run.stderr)
            check("the reference holds the client's rows",
                  cluster.value("SELECT count(*) FROM res_partner", "ACME_original") == "1")
            check("the restore's errors are kept for classification",
                  planners.intake_restore_stderr(env).exists())

            # --- the reader role, run ----------------------------------------------------
            columns = [(t, c) for t, c in (line.split("\t") for line in cluster.value(
                "SELECT c.relname, a.attname FROM pg_attribute a JOIN pg_class c ON "
                "c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace WHERE "
                "n.nspname = 'public' AND c.relkind = 'r' AND a.attnum > 0 AND NOT "
                "a.attisdropped", "ACME_original").splitlines())]
            grants = intake.reader_role_sql("acme_reader", "ACME_original", columns)
            home = root / "home"
            home.mkdir()
            fake = root / "fakebin"
            fake.mkdir()
            (fake / "sudo").write_text('#!/bin/bash\nshift 3\nexec "$@"\n')  # drops -n -u postgres
            (fake / "sudo").chmod(0o755)
            env_run = {**pg, "HOME": str(home), "PATH": f"{fake}:{pg['PATH']}"}
            plan = planners.plan_reader_role(env, "ACME_original", "acme_reader", grants, True)
            check("the role plan carries no password", not any(
                c for c in plan if any(len(w) == 48 for w in c.command.split())))
            for command in plan:
                run = _bash(command.command, env_run)
                check(f"role plan: {command.description}", run.returncode == 0, run.stderr)
            pgpass = home / ".pgpass"
            line = pgpass.read_text().strip() if pgpass.exists() else ""
            check("the password is in .pgpass, mode 600",
                  pgpass.exists() and oct(pgpass.stat().st_mode)[-3:] == "600"
                  and len(line.rsplit(":", 1)[-1]) == 48, line[:20])
            as_reader = {**pg, "HOME": str(home), "PGUSER": "acme_reader",
                         "PGHOST": str(cluster.sock), "PGPASSFILE": str(pgpass)}

            def reader(sql: str) -> subprocess.CompletedProcess[str]:
                return _bash(f"psql -X -w -At -d ACME_original -c \"{sql}\"", as_reader)

            check("the role logs in with the password it was given",
                  reader("SELECT count(*) FROM res_partner").stdout.strip() == "1",
                  reader("SELECT 1").stderr)
            check("it cannot read a password or a system parameter's value",
                  "permission denied" in reader("SELECT password FROM res_users").stderr
                  and "permission denied" in reader("SELECT value FROM ir_config_parameter").stderr)
            check("it cannot write, even with read-only switched off",
                  "permission denied" in reader(
                      "SET default_transaction_read_only = off; BEGIN READ WRITE; "
                      "UPDATE res_partner SET name = 'x'; COMMIT").stderr)
            check("it reads where a sequence stands (a wizard's only trace)",
                  reader("SELECT is_called FROM res_partner_id_seq").stdout.strip() == "t",
                  reader("SELECT 1 FROM res_partner_id_seq").stderr)
            check("it cannot advance a sequence",
                  "permission denied" in reader("SELECT nextval('res_partner_id_seq')").stderr)
            again = planners.plan_reader_role(env, "ACME_original", "acme_reader", grants, True)
            _bash(again[0].command, env_run)  # a second creation fails: the role exists
            check("a second run leaves one .pgpass line for the role",
                  pgpass.read_text().count("acme_reader") == 1)

            # --- the uninstall comparison, on two real databases -----------------------------
            cluster.sql("CREATE DATABASE ub")
            cluster.value("""
                CREATE TABLE ir_model (id serial, model varchar, transient boolean);
                CREATE TABLE ir_model_data (id serial, module varchar, model varchar, res_id int);
                CREATE TABLE ir_model_fields (id serial, model varchar, name varchar,
                                              store boolean, related varchar);
                CREATE TABLE ir_module_module (id serial, name varchar, state varchar);
                CREATE TABLE ir_ui_view (id serial, name varchar);
                CREATE TABLE aeat_model_export_config (id serial, name varchar);
                CREATE TABLE invoice_merge (id serial);
                CREATE TABLE purchase_order (id serial, commercial_partner_id int, note_x int,
                                             flag boolean DEFAULT false);
                INSERT INTO ir_model (model, transient) VALUES ('invoice.merge', true);
                INSERT INTO ir_model_data (module, model, res_id) VALUES
                  ('mod_a', 'aeat.model.export.config', 1), ('mod_a', 'aeat.model.export.config', 2);
                INSERT INTO ir_model_fields (model, name, store, related) VALUES
                  ('purchase.order', 'commercial_partner_id', true, 'partner_id.commercial_partner_id');
                INSERT INTO ir_module_module (name, state) VALUES ('base', 'installed'),
                  ('mod_a', 'installed'), ('mod_dep', 'installed'), ('mod_c', 'installed');
                INSERT INTO ir_ui_view (name) SELECT 'v' FROM generate_series(1, 5);
                INSERT INTO aeat_model_export_config (name) VALUES ('a'), ('b'), ('user');
                INSERT INTO invoice_merge DEFAULT VALUES;
                INSERT INTO purchase_order (commercial_partner_id, note_x) VALUES (1, 7), (2, NULL);
                SELECT 1""", "ub")
            cluster.sql("CREATE DATABASE ua TEMPLATE ub")
            cluster.value("""
                DELETE FROM aeat_model_export_config WHERE name IN ('a', 'b');
                DROP TABLE invoice_merge;
                DELETE FROM ir_ui_view WHERE id > 3;
                ALTER TABLE purchase_order DROP COLUMN commercial_partner_id, DROP COLUMN flag;
                UPDATE ir_module_module SET state = 'uninstalled' WHERE name IN ('mod_a', 'mod_dep');
                SELECT 1""", "ua")
            cluster.value("""
                CREATE TABLE ir_module_module_dependency (id serial, module_id int, name varchar);
                INSERT INTO ir_module_module_dependency (module_id, name)
                  SELECT id, 'mod_a' FROM ir_module_module WHERE name = 'mod_dep';
                INSERT INTO ir_module_module (name, state) VALUES ('mod_dep2', 'installed'),
                  ('mod_gone', 'uninstalled');
                INSERT INTO ir_module_module_dependency (module_id, name)
                  SELECT id, 'mod_dep' FROM ir_module_module WHERE name IN ('mod_dep2', 'mod_gone');
                SELECT 1""", "ub")
            deps = system.psql_rows(intake.dependents_sql(["mod_a"]), "ub", str(cluster.sock),
                                    cluster.port, "postgres")
            check("the dependents are found before any uninstall, transitively, installed only",
                  deps == [["mod_dep"], ["mod_dep2"]], deps)
            cluster.value("DELETE FROM ir_module_module WHERE name = 'mod_dep2'; SELECT 1", "ub")
            # A manifest's author spread over lines split a module's row in two, and
            # the driver checked the second line as a module: the query flattens it.
            cluster.value("ALTER TABLE ir_module_module ADD COLUMN author varchar; "
                          "UPDATE ir_module_module SET author = E'Someone,\\n    Odoo Community "
                          "Association (OCA)' WHERE name = 'mod_c'; SELECT 1", "ub")
            from odoo_dwg import templates  # noqa: PLC0415
            driver = templates.render_run_migration_sh(env)
            line = next(x for x in driver.splitlines() if "step_modules=$(psql" in x)
            query = line.split("step_modules=", 1)[1].split(" || die", 1)[0]
            listed = _bash(f'DB=ub; v={query}; printf "%s\\n" "$v"', pg).stdout.splitlines()
            check("the driver's module list has one row per module, whatever an author holds",
                  "mod_c\tSomeone,     Odoo Community Association (OCA)" in listed
                  and all("\t" in row for row in listed if row), listed)
            cluster.value("ALTER TABLE ir_module_module DROP COLUMN author; SELECT 1", "ub")
            from odoo_dwg.workflows import intake as wf_intake  # noqa: PLC0415
            compared = wf_intake._compare_uninstall(env, "ub", "ua", ["mod_a"])
            kinds = {(c.table, c.column): c.kind for c in (compared or ([], []))[0]}
            check("the comparison reads both databases and names every difference",
                  compared is not None and kinds == {
                      ("aeat_model_export_config", ""): "module data",
                      ("invoice_merge", ""): "wizard", ("ir_ui_view", ""): "metadata",
                      ("purchase_order", "commercial_partner_id"): "recomputed",
                      ("purchase_order", "flag"): "empty",  # a false is no value
                      ("ir_module_module", ""): "metadata",
                      ("ir_module_module_dependency", ""): "metadata"}, kinds)
            check("it names the dependent the uninstall took along",
                  compared is not None and compared[1] == ["mod_dep"], compared)
            cluster.value("ALTER TABLE purchase_order DROP COLUMN note_x; "
                          "DELETE FROM aeat_model_export_config; SELECT 1", "ua")
            compared = wf_intake._compare_uninstall(env, "ub", "ua", ["mod_a"])
            lost = {(c.table, c.column): c.before for c in (compared or ([], []))[0]
                    if c.kind == "data lost"}
            check("a dropped column with a value, and a row beyond what was owned, are data lost",
                  lost == {("purchase_order", "note_x"): 1, ("aeat_model_export_config", ""): 3},
                  lost)

            # --- the audit of the client's own modules, on a real database --------------------
            cluster.sql("CREATE DATABASE audit")
            cluster.value(AUDIT_DB + " SELECT 1", "audit")
            from odoo_dwg.workflows import intake as wf_audit  # noqa: PLC0415
            audited = wf_audit._audit_module_rows(env, "audit", ["acme"], "2025-01-01", None) or []
            got = {(r.kind, r.subject): (r.total, r.since, r.last) for r in audited}
            check("the audit counts values (not false, not ''), use since the date, and the last",
                  got.get(("field", "res.partner.acme_flag")) == ("2", "1", "2026-02-01")
                  and got.get(("field", "res.partner.acme_note")) == ("1", "1", "2026-02-01")
                  and got.get(("model", "acme.thing")) == ("1", "0", "2022-01-01"), got)
            check("a wizard's openings come from its sequence; a dependent and a document's "
                  "attachments are found",
                  got.get(("wizard", "acme.wizard"), ("",))[0] == "2"
                  and got.get(("dependent", "acme_extra")) == ("", "", "")
                  and got.get(("document", "acme.invoice")) == ("2", "1", ""), got)
            trap = next((r.note for r in audited if r.kind == "document"), "")
            check("a document registered under another module's namespace is flagged",
                  "registered as account.*" in trap, trap)

            # --- bank statement lines imported twice, on a real database ------------------------
            cluster.sql("CREATE DATABASE bank")
            cluster.value(BANK_DB + " SELECT 1", "bank")
            q = {"host": env.db_host, "port": env.db_port, "user": env.db_user}
            copies = intake.parse_bank_copies(
                system.psql_rows(intake.BANK_DUPLICATES_SQL, "bank", **q) or [])
            got = {(c.kind, c.line, c.kept) for c in copies}
            check("a bank day imported twice: each unreconciled copy is a duplicate of the kept one",
                  {("duplicate", 6, 3), ("duplicate", 7, 4)} <= got, got)
            check("two equal fees in one day stay two movements; a movement reconciled in both "
                  "copies is recorded apart",
                  ("reconciled twice", 5, 2) in got and not any(c.line in (2, 3) for c in copies),
                  got)
            check("a statement that does not match its file proves nothing",
                  not any(c.line in (8, 9) for c in copies) and len(copies) == 3, got)
            stats = system.psql_rows(intake.BANK_LINES_STATS_SQL, "bank", **q)
            check("statements matching their file, unreconciled lines, and those after the lock",
                  stats == [["3", "2", "9", "6", "2"]], stats)
            guarded = intake.bank_duplicates_sql(copies)
            first = cluster.sql(guarded, "bank")
            second = cluster.sql(guarded, "bank")
            left = cluster.value("SELECT string_agg(id::text, ',' ORDER BY id) "
                                 "FROM account_bank_statement_line", "bank")
            check("the guarded SQL deletes the duplicates only, and a second run deletes nothing",
                  "DELETE 2" in first.stdout and "DELETE 0" in second.stdout
                  and left == "1,2,3,4,5,8,9", (first.stdout, second.stdout, left))

            # --- the uninstall command, against a stub interpreter ---------------------------
            record = intake.IntakeRecord("ACME_original", "acme_reader", "client-src/acme",
                                         ("custom",), intake.Core("ocb", "a" * 40))
            with_intake = MigrationEnv(source="12.0", target="18.0", db_host=str(cluster.sock),
                                       db_port=cluster.port, db_user="postgres", intake=record)
            stub = with_intake.venv_dir("12.0") / "bin" / "python"
            stub.parent.mkdir(parents=True, exist_ok=True)
            stub.write_text(f'#!/bin/bash\nprintf "%s\\n" "$@" > {root}/args\n'
                            f"cat > {root}/script.py\n")
            stub.chmod(0o755)
            plan = planners.plan_uninstall_rehearsal(with_intake, "ub", "ub_uninstall",
                                                     ["mod_a", "mod_c"])
            ran = _bash(plan[2].command)
            args = (root / "args").read_text().split("\n") if (root / "args").exists() else []
            script = (root / "script.py").read_text() if (root / "script.py").exists() else ""
            check("odoo-bin shell gets the throwaway database, no HTTP, no cron thread",
                  ran.returncode == 0 and "shell" in args and "ub_uninstall" in args
                  and "--no-http" in args and "--max-cron-threads=0" in args, (ran.stderr, args))
            check("the script reaches its stdin intact",
                  script == planners.uninstall_script(["mod_a", "mod_c"]), script)

            class _Mods(list):
                def mapped(self, _field):
                    return list(self)

                def button_immediate_uninstall(self):
                    calls.append(sorted(self))

            class _Cr:
                def __init__(self, left):
                    self.left = left

                def commit(self):
                    calls.append("commit")

                def execute(self, *_a):
                    pass

                def fetchall(self):
                    return [(n,) for n in self.left]

            def run_script(installed, left):
                shell_env = type("Env", (), {"cr": _Cr(left)})()
                shell_env.__class__.__getitem__ = lambda _s, _m: type(
                    "Model", (), {"search": staticmethod(lambda _d: _Mods(installed))})()
                try:
                    exec(script, {"env": shell_env})  # noqa: S102 — the script under test
                except SystemExit as stop:
                    return str(stop)
                return "ok"

            calls: list = []
            check("the script uninstalls, commits, and confirms",
                  run_script(["mod_a", "mod_c"], []) == "ok"
                  and calls == [["mod_a", "mod_c"], "commit"], calls)
            calls = []
            check("a module that is not installed stops it before any uninstall",
                  "not installed: mod_c" in run_script(["mod_a"], []) and calls == [], calls)
            check("a module still installed after is a failure",
                  "still installed: mod_c" in run_script(["mod_a", "mod_c"], ["mod_c"]))
        finally:
            cluster.stop()

        # --- a history with a merge ------------------------------------------------------
        repo = root / "odoo"
        git = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}

        def g(*args: str, when: str = "2021-01-01T00:00:00") -> None:
            run = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                                 env={**os.environ, **git, "GIT_AUTHOR_DATE": when,
                                      "GIT_COMMITTER_DATE": when})
            if run.returncode != 0 and "CONFLICT" not in run.stdout:
                raise SystemExit(f"git {' '.join(args)}: {run.stderr}")

        def put(path: str, text: str) -> None:
            file = repo / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text)

        repo.mkdir()
        g("init", "-q", "-b", "12.0")
        put("addons/web/a.py", "a1\n")
        put("odoo/addons/base/b.py", "b1\n")
        g("add", "-A")
        g("commit", "-q", "-m", "base", when="2021-01-01T00:00:00")
        g("checkout", "-q", "-b", "feature")
        put("odoo/addons/base/b.py", "b-feature\n")
        g("commit", "-q", "-am", "feature", when="2021-02-01T00:00:00")
        g("checkout", "-q", "12.0")
        put("odoo/addons/base/b.py", "b-main\n")
        g("commit", "-q", "-am", "main", when="2021-02-02T00:00:00")
        g("merge", "-q", "--no-ff", "feature", "-m", "merge", when="2021-03-01T00:00:00")
        put("odoo/addons/base/b.py", "b-resolved-by-the-merge\n")
        g("add", "-A")
        g("commit", "-q", "-m", "merge", when="2021-03-01T00:00:00")
        merge = (system.git_output(repo, "rev-parse", "HEAD") or "").strip()
        # The client runs the merge; the branch then moves on.
        client_dir = root / "client-core"
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(client_dir), merge],
                       capture_output=True)
        (client_dir / "addons" / "web" / "views.xml_backup").write_text("stray\n")
        # The branch moves on, past both files, so both differ from its head.
        put("addons/web/a.py", "a2\n")
        put("odoo/addons/base/b.py", "b-later\n")
        g("commit", "-q", "-am", "later", when="2021-06-01T00:00:00")

        client = system.tree_blobs(client_dir)
        head = intake.parse_ls_tree(system.git_output(repo, "ls-tree", "-r", "HEAD") or "")
        hashed = (system.git_output(repo, "hash-object", str(client_dir / "addons/web/a.py"))
                  or "").strip()
        check("git_blob_id agrees with git hash-object", client["addons/web/a.py"] == hashed)
        differing = sorted(p for p, b in client.items() if p in head and head[p] != b)
        history = intake.parse_raw_log(system.git_raw_log(repo, differing) or "")
        without_merges = intake.parse_raw_log(system.git_output(
            repo, "log", "--raw", "--no-abbrev", "--no-renames", "--format=@%H %cs", "HEAD",
            "--", *differing) or "")
        check("the version only a merge produced is found with merges, and not without",
              ("odoo/addons/base/b.py", client["odoo/addons/base/b.py"]) in history
              and ("odoo/addons/base/b.py", client["odoo/addons/base/b.py"])
              not in without_merges)
        commits = (system.git_output(repo, "rev-list", "--first-parent", "HEAD") or "").split()
        trees = [(c, intake.parse_ls_tree(system.git_output(repo, "ls-tree", "-r", c) or ""))
                 for c in intake.sample(commits, 150)]
        match = intake.best_commit(client, trees)
        # The client's stray backup file counts once, and nothing else differs.
        check("the closest commit is the merge the client runs",
              match is not None and match.commit == merge and match.differences == 1
              and match.client_only == ("addons/web/views.xml_backup",), match)
        tree = dict(trees)[merge]
        verdict = intake.core_identity(client, "odoo", merge, tree, {"odoo": history})
        check("the core is identified, the stray file set apart",
              verdict.flavour == "odoo" and verdict.patched == () and verdict.differing == ()
              and verdict.client_only == ("addons/web/views.xml_backup",), verdict)
        patched = {**client, "addons/web/a.py": intake.git_blob_id(b"a-patched-locally\n")}
        residual = ["addons/web/a.py"]
        local = intake.core_identity(patched, "odoo", merge, tree, {"odoo": intake.parse_raw_log(
            system.git_raw_log(repo, residual) or "")})
        check("a file no commit ever had is a local patch, by path",
              local.flavour == "patched" and local.patched == ("addons/web/a.py",), local)

        # --- modules along the chain, on real OCA-like repositories ----------------------
        org = root / "OCA"
        layout = {  # repo -> version -> modules
            "web": {"13.0": ["web_moved", "web_kept"], "14.0": ["web_kept"]},
            "web-extra": {"14.0": ["web_moved"]},
            "account-invoicing": {"12.0": ["never_ported"]},   # no 13.0 or 14.0 branch
        }
        for repo, versions in layout.items():
            work = root / "work" / repo
            work.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(work)], check=True)
            for version, modules in versions.items():
                subprocess.run(["git", "-C", str(work), "checkout", "-q", "--orphan", version],
                               check=True)
                subprocess.run(["git", "-C", str(work), "rm", "-rqf", "--ignore-unmatch", "."],
                               check=True, capture_output=True)
                for module in modules:
                    (work / module).mkdir(exist_ok=True)
                    (work / module / "__manifest__.py").write_text("{}\n")
                subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
                subprocess.run(["git", "-C", str(work), "commit", "-qm", version], check=True,
                               env={**os.environ, **git})
            subprocess.run(["git", "clone", "-q", "--bare", str(work), str(org / f"{repo}.git")],
                           check=True)
        want = {"web": ["13.0", "14.0"], "web-extra": ["13.0", "14.0"],
                "account-invoicing": ["13.0", "14.0"]}
        for command in planners.plan_oca_trees(env, want, base=f"file://{org}"):
            run = _bash(command.command)
            check(f"tree plan: {command.description}", run.returncode == 0, run.stderr)
        absent = planners.oca_tree_dir(env, "account-invoicing", "13.0")
        check("a branch that does not exist is remembered as absent, not cloned",
              Path(f"{absent}.absent").exists() and not absent.exists())
        found = {v: {} for v in ("13.0", "14.0")}
        for repo in layout:
            for version in found:
                tree = planners.oca_tree_dir(env, repo, version)
                if tree.is_dir():
                    for module in system.tree_modules(tree):
                        found[version].setdefault(module, repo)
        rows = {r.module: r for r in intake.availability(
            {"web_moved": ("oca", "web"), "never_ported": ("oca", "account-invoicing")},
            [], ["13.0", "14.0"], found)}
        check("a module that moved repository is found at every step, and marked moved",
              rows["web_moved"].where == ("web", "web-extra") and rows["web_moved"].moved)
        check("a module no repository ports is a gap at every step",
              rows["never_ported"].gaps == (0, 1))
        broken = planners.plan_oca_trees(env, {"web": ["15.0"]}, base="file:///nonexistent/OCA")
        failed = _bash(broken[0].command)
        check("an unreachable remote stops the step instead of being taken for an absent branch",
              failed.returncode != 0 and not Path(f"{planners.oca_tree_dir(env, 'web', '15.0')}"
                                                  ".absent").exists(), failed.returncode)

        # --- the filestore ---------------------------------------------------------------
        store = root / "fs-src" / "whatever" / "ACME"
        # As Odoo lays it out: the buckets, and checklist/ with as many buckets of
        # its own. Choosing by count once took checklist/ for the filestore.
        for bucket in ("0a", "ff"):
            (store / bucket).mkdir(parents=True)
            (store / bucket / f"{bucket}cafe").write_text("attachment\n")
            (store / "checklist" / bucket).mkdir(parents=True)
            (store / "checklist" / bucket / f"{bucket}cafe").write_text("")
        archive = root / "filestore.tar.gz"
        _bash(f"tar -czf {archive} -C {root / 'fs-src'} whatever")
        for command in planners.plan_unpack_filestore(env, archive, "ACME_original"):
            run = _bash(command.command)
            check(f"filestore plan: {command.description}", run.returncode == 0, run.stderr)
        target = env.data_dir / "filestore" / "ACME_original"
        check("the buckets land in data/filestore/<reference>, checklist inside, scaffolding gone",
              (target / "0a" / "0acafe").exists() and (target / "ff").is_dir()
              and (target / "checklist" / "0a").is_dir()
              and not any(p.name.startswith(".incoming") for p in target.parent.iterdir()))

    if failures:
        print(f"\n{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nTaking in a client copy does what it says, on real tools.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
