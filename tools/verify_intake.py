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
            again = planners.plan_reader_role(env, "ACME_original", "acme_reader", grants, True)
            _bash(again[0].command, env_run)  # a second creation fails: the role exists
            check("a second run leaves one .pgpass line for the role",
                  pgpass.read_text().count("acme_reader") == 1)
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
