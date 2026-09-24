"""Taking in a client copy, from the menu.

Each step changes the host through a previewed plan, then records what it found
— ``intake.json``, data tables under ``findings/data/`` and findings in the
ledger — through a second previewed plan. Findings are recorded ``internal`` and
in English: the client-facing text is the operator's to write.
"""

from __future__ import annotations

import csv
import io
import json
import shlex
from dataclasses import replace
from datetime import date
from pathlib import Path

from .. import findings as fl
from .. import intake as it
from .. import neutralise, planners, preflight
from ..i18n import t, tf
from ..models import DB_NAME_RE, Command, MigrationEnv
from ..planners import write_text_file_command
from ..prompts import ask_text, choose, confirm_with_phrase
from ..system import (
    archive_top,
    git_output,
    git_raw_log,
    github_org_repos,
    psql_rows,
    psql_scalar,
    read_text,
    repo_state,
    run,
    scan_manifests,
    tree_blobs,
    tree_modules,
)
from ..ui import level_text, render_table
from .common import apply_if_confirmed, armed_state, mail_state

#: Commits compared per history before refining between the best sample's
#: neighbours. A tree listing costs a few hundredths of a second, so a whole
#: branch is sampled, and the stretch refined, in about a minute.
CORE_SAMPLES = 150


# --- the record ------------------------------------------------------------------------

def load_intake(env: MigrationEnv) -> it.IntakeRecord | None:
    """The environment's intake record, None without one. An unreadable record is
    refused, not half-used: raising stops the flow that asked for it."""
    text = read_text(str(env.intake_file))
    if text is None:
        return None
    return it.parse_intake(text)


def _tsv(rows: list[list[str]]) -> str:
    out = io.StringIO()
    csv.writer(out, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE,
               escapechar="\\").writerows(rows)
    return out.getvalue()


def _finding(fid: str, severity: str, subject: str, summary: str, evidence: object,
             query: str, action: str) -> dict:
    today = date.today().isoformat()
    return {"id": fid, "found": today, "phase": "intake", "severity": severity,
            "category": "intake", "audience": "internal", "subject": subject,
            "summary": summary, "evidence": evidence or {"note": "none"}, "query": query,
            "action": action, "decision": {"state": "pending", "date": today, "note": ""}}


def _record(env: MigrationEnv, record: it.IntakeRecord, found: list[dict],
            tables: dict[str, list[list[str]]]) -> None:
    """Write the record, the tables and the new findings, through one previewed plan."""
    ledger_text = read_text(str(env.findings_ledger))
    if ledger_text is None:
        client = ask_text("Client name (for the findings ledger)", required=True)
        ledger = fl.new_ledger(client, record.reference_database.removesuffix("_original"),
                               env.source, env.target, record.reference_database)
    else:
        ledger = fl.parse_ledger(ledger_text)
    known = {f.id for f in ledger.findings} | {c.withdrawn for c in ledger.corrections}
    fresh = [f for f in found if f["id"] not in known]
    for f in found:
        if f["id"] in known:
            print(level_text("INFO", tf("Finding {} is already in the ledger; left as it is.",
                                        f["id"])))
    if fresh:
        ledger = fl.add_findings(ledger, fl.parse_findings(json.dumps(fresh)))
    commands = [Command(tf("Create {}", str(env.findings_data_dir)),
                        f"mkdir -p {shlex.quote(str(env.findings_data_dir))}")]
    for name, rows in tables.items():
        commands += write_text_file_command(env.findings_data_dir / name, _tsv(rows))
    commands += write_text_file_command(env.intake_file, it.dump_intake(record))
    commands += write_text_file_command(env.findings_ledger, fl.dump_ledger(ledger))
    for f in found:
        print(f"  {f['severity']:<9} {f['id']}: {f['summary'][:110]}")
    if apply_if_confirmed(commands):
        print(level_text("OK", tf("Intake recorded: {}", str(env.intake_file))))


def _current(env: MigrationEnv) -> it.IntakeRecord | None:
    if env.intake is None:
        print(level_text("INFO", t("No intake yet: restore the client's dump first.")))
    return env.intake


def _replace(record: it.IntakeRecord, **changes) -> it.IntakeRecord:
    return replace(record, **changes)


# --- steps -----------------------------------------------------------------------------

def _database_exists(env: MigrationEnv, name: str) -> bool | None:
    value = psql_scalar(f"SELECT count(*) FROM pg_database WHERE datname = '{name}'", "postgres",
                        env.db_host, env.db_port, env.db_user)
    return None if value is None else value != "0"


def restore_dump(env: MigrationEnv) -> None:
    dump = Path(ask_text("Client dump (pg_dump -Fc)", required=True)).expanduser()
    if not dump.is_file():
        print(level_text("ERROR", tf("Cannot read {}.", str(dump))))
        return
    reference = ask_text("Reference database (never modified)", f"{dump.stem}_original")
    if not DB_NAME_RE.fullmatch(reference):
        print(level_text("ERROR", tf("Invalid database name: {}", reference)))
        return
    if _database_exists(env, reference) is not False:
        print(level_text("ERROR", tf("Database {} exists (or cannot be checked); it is not "
                                     "replaced.", reference)))
        return
    if not apply_if_confirmed(planners.plan_intake_restore(env, dump, reference)):
        return
    toc = run(f"pg_restore -l {shlex.quote(str(dump))}").stdout
    expected = sum(1 for line in toc.splitlines() if " TABLE DATA " not in line and " TABLE " in line)
    restored = psql_scalar("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'",
                           reference, env.db_host, env.db_port, env.db_user) or "?"
    stderr = read_text(str(planners.intake_restore_stderr(env))) or ""
    verdicts = it.classify(it.parse_restore_errors(stderr))
    found = [_finding(
        "intake-restore", "info", reference,
        f"Restored {dump.name} into {reference}: {restored} tables of {expected} in the dump's "
        f"table of contents, {len(verdicts)} restore error(s).",
        {"tables_restored": restored, "tables_in_dump": expected, "errors": len(verdicts)},
        f"pg_restore -l {dump.name}; select count(*) from pg_tables where schemaname='public'",
        "none if the counts agree")]
    for index, (error, known) in enumerate(verdicts, 1):
        if known is not None:
            found.append(_finding(f"intake-restore-{known.id}", "low", "pg_restore",
                                  f"{known.reason}", {"error": error.message,
                                                      "command": error.command[:300],
                                                      "source": known.source},
                                  "the restore's stderr, findings/data/intake-restore.stderr",
                                  "none for the data; note it for the rehearsal"))
        else:
            found.append(_finding(f"intake-restore-unknown-{index}", "high", "pg_restore",
                                  f"A restore error of no known class: {error.message}",
                                  {"error": error.message, "command": error.command[:300]},
                                  "the restore's stderr, findings/data/intake-restore.stderr",
                                  "find out what it lost before relying on the reference"))
    if str(restored) != str(expected):
        print(level_text("WARN", tf("{} tables restored of {} in the dump: the reference may be "
                                    "incomplete.", restored, str(expected))))
    record = env.intake or it.IntakeRecord(reference)
    _record(env, _replace(record, reference_database=reference), found, {})


def create_reader(env: MigrationEnv) -> None:
    record = _current(env)
    if record is None:
        return
    role = ask_text("Read-only role", f"{record.reference_database.lower().removesuffix('_original')}_reader")
    if not DB_NAME_RE.fullmatch(role):
        print(level_text("ERROR", tf("Invalid database name: {}", role)))
        return
    exists = psql_scalar(f"SELECT count(*) FROM pg_roles WHERE rolname = '{role}'", "postgres",
                         env.db_host, env.db_port, env.db_user)
    rows = psql_rows("SELECT c.relname, a.attname FROM pg_attribute a JOIN pg_class c ON "
                     "c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace WHERE "
                     "n.nspname = 'public' AND c.relkind = 'r' AND a.attnum > 0 AND NOT "
                     "a.attisdropped", record.reference_database, env.db_host, env.db_port,
                     env.db_user)
    if exists is None or rows is None:
        print(level_text("ERROR", tf("Could not read database {}.", record.reference_database)))
        return
    columns = [(r[0], r[1]) for r in rows if len(r) >= 2]
    grants = it.reader_role_sql(role, record.reference_database, columns)
    hidden = it.hidden_columns(columns)
    print(level_text("INFO", tf("{} column(s) will be hidden from {}.", str(len(hidden)), role)))
    if not apply_if_confirmed(planners.plan_reader_role(env, record.reference_database, role,
                                                        grants, create=exists == "0")):
        return
    _record(env, _replace(record, reader_role=role), [_finding(
        "intake-reader-role", "info", role,
        f"Read-only role {role} on {record.reference_database}: SELECT only, read-only by "
        f"default, no TEMP, {len(hidden)} secret column(s) hidden; password in ~/.pgpass only.",
        {"hidden_columns": len(hidden)}, f"psql -h {env.db_host} -U {role} "
        f"{record.reference_database}", "none")],
        {"intake-hidden-columns.tsv": [["table", "column"], *[[a, b] for a, b in hidden]]})


def unpack_archive(env: MigrationEnv) -> None:
    record = _current(env)
    if record is None:
        return
    archive = Path(ask_text("Client add-ons archive (.tar/.tar.gz)", required=True)).expanduser()
    top = archive_top(archive) if archive.is_file() else None
    if top is None:
        print(level_text("ERROR", tf("Cannot read {}.", str(archive))))
        return
    if (env.client_src_dir / top).exists():
        print(level_text("ERROR", tf("{} already exists; it is not replaced.",
                                     str(env.client_src_dir / top))))
        return
    if apply_if_confirmed(planners.plan_unpack_archive(env, archive, top)):
        _record(env, _replace(record, archive_root=f"client-src/{top}"), [], {})


def _archive_dirs(root: Path, depth: int = 4) -> tuple[set[str], set[str]]:
    dirs, has_base = set(), set()
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if path.is_dir() and len(rel.parts) <= depth and ".git" not in rel.parts:
            dirs.add(str(rel))
            if any((path / "base" / m).is_file() for m in it.MANIFESTS):
                has_base.add(str(rel))
    return dirs, has_base


def classify_archive(env: MigrationEnv) -> None:
    record = _current(env)
    if record is None or not record.archive_root:
        print(level_text("INFO", t("Unpack the client's add-ons archive first.")))
        return
    conf = read_text(str(Path(ask_text("Client odoo.conf", required=True)).expanduser()))
    if conf is None:
        print(level_text("ERROR", t("Cannot read the configuration file.")))
        return
    root = env.root / record.archive_root
    dirs, has_base = _archive_dirs(root)
    layout = it.archive_layout(it.conf_addons_path(conf), dirs, has_base)
    installed = psql_rows("SELECT name FROM ir_module_module WHERE state = 'installed'",
                          record.reference_database, env.db_host, env.db_port, env.db_user)
    if installed is None:
        print(level_text("ERROR", tf("Could not read database {}.", record.reference_database)))
        return
    modules = it.classify_modules(scan_manifests(root, list(layout.dirs)),
                                  {r[0] for r in installed if r})
    needs: dict[str, list[str]] = {}
    unreadable = []
    for module in sorted(r[0] for r in installed if r):
        where = modules.loads_from.get(module)
        if where is None:
            continue
        manifest = next((root / where / module / m for m in it.MANIFESTS
                         if (root / where / module / m).is_file()), None)
        imports = it.manifest_python_imports(read_text(str(manifest)) or "") if manifest else []
        if imports is None:
            unreadable.append(module)
            continue
        for name in imports:
            needs.setdefault(name, []).append(module)
    python_deps = it.pip_names(list(needs))
    repos = [[d, *(repo_state(root / d).get(k, "") for k in
                   ("remote", "branch", "head", "last_commit", "upstream", "ahead", "behind",
                    "dirty"))] for d in layout.client_dirs]
    installed_rows = [[m, modules.loads_from.get(m, "MISSING")]
                      for m in sorted(r[0] for r in installed if r)]
    found = [_finding(
        "intake-archive", "info", record.archive_root,
        f"{len(layout.dirs)} addons_path directories mapped ({len(layout.missing)} missing), "
        f"core at '{layout.core_root}', {len(modules.loads_from)} modules, "
        f"{len(installed_rows)} installed.",
        {"dirs": len(layout.dirs), "missing": list(layout.missing), "core_root": layout.core_root,
         "duplicates": modules.duplicates, "legacy_manifest": list(modules.legacy_manifest)},
        "findings/data/intake-repos.tsv, intake-installed.tsv", "none")]
    if modules.installed_without_code:
        found.append(_finding("intake-installed-without-code", "high", "ir_module_module",
                              "Installed modules whose code is in no addons_path directory.",
                              {"modules": list(modules.installed_without_code)},
                              "findings/data/intake-installed.tsv (MISSING)",
                              "find the code or uninstall before the chain"))
    for row in repos:
        if row[8]:
            found.append(_finding(f"intake-uncommitted-{row[0].replace('/', '-').lower()}",
                                  "medium", row[0],
                                  "Production runs changes this repository does not hold.",
                                  {"files": row[8].split(";"), "last_commit": row[4]},
                                  f"git -C client-src/.../{row[0]} status --porcelain",
                                  "port from the archive, not from the repository"))
    if unreadable:
        found.append(_finding("intake-unreadable-manifests", "medium", "manifests",
                              "Installed modules whose manifest is not a plain dict literal: "
                              "their Python dependencies were not read.",
                              {"modules": unreadable}, "ast.literal_eval of each manifest",
                              "read them by hand and add what they need"))
    _record(env, _replace(record, addons_dirs=layout.client_dirs, core_dir=layout.core_root or "",
                          python_deps=python_deps), found, {
        "intake-python-deps.tsv": [["import", "pip", "modules"],
                                   *[[name, it.PIP_NAMES.get(name, name), ",".join(mods)]
                                     for name, mods in sorted(needs.items())]],
        "intake-repos.tsv": [["dir", "remote", "branch", "head", "last_commit", "upstream",
                              "ahead", "behind", "uncommitted"], *repos],
        "intake-installed.tsv": [["module", "loads_from"], *installed_rows],
    })


def _first_parent(repo: Path) -> list[tuple[str, str]]:
    """``(commit, date)`` of a branch's first-parent line, newest first."""
    text = git_output(repo, "log", "--first-parent", "--format=%H %cs", "HEAD") or ""
    return [(c, d) for c, _, d in (line.partition(" ") for line in text.splitlines()) if d]


def _tree(repo: Path, commit: str) -> dict[str, str]:
    return it.parse_ls_tree(git_output(repo, "ls-tree", "-r", commit, "--", "addons",
                                       "odoo/addons") or "")


def identify_core(env: MigrationEnv) -> None:
    """Official Odoo or OCB, and which commit: the closest tree first, then the few
    files that still differ looked up in both histories."""
    record = _current(env)
    if record is None or not record.archive_root:
        print(level_text("INFO", t("Classify the client's add-ons archive first.")))
        return
    core_root = env.root / record.archive_root / record.core_dir
    repos = {f: env.history_dir / f"{f}-{env.source}" for f in it.FLAVOURS}
    missing = [f for f, repo in repos.items() if not repo.is_dir()]
    if missing and not apply_if_confirmed(
            [c for f in missing for c in planners.plan_history(env, f, env.source)]):
        return
    client = tree_blobs(core_root)
    if not client:
        print(level_text("ERROR", tf("No core add-ons under {}.", str(core_root))))
        return
    lines = {f: _first_parent(repo) for f, repo in repos.items()}
    print(level_text("INFO", tf("Comparing the client's core with {} sampled commits…",
                                str(sum(min(len(v), CORE_SAMPLES) for v in lines.values())))))
    best: tuple[str, it.CommitMatch] | None = None
    for flavour in it.FLAVOURS:  # official first: on a tie it wins
        commits = [c for c, _ in lines[flavour]]
        samples = it.sample(commits, CORE_SAMPLES)
        match = it.best_commit(client, [(c, _tree(repos[flavour], c)) for c in samples])
        if match is None:
            continue
        # The true commit lies between the best sample's neighbours: refine by
        # position, not by date. A branch's commits are not spread evenly in time —
        # most of 12.0's are from its first two years — so a window of days around
        # the best sample missed a commit that was only one sample away.
        at = samples.index(match.commit)
        lo = commits.index(samples[at - 1]) if at > 0 else 0
        hi = commits.index(samples[at + 1]) + 1 if at + 1 < len(samples) else len(commits)
        match = it.best_commit(client, [(c, _tree(repos[flavour], c))
                                        for c in commits[lo:hi]]) or match
        if best is None or match.differences < best[1].differences:
            best = (flavour, match)
    if best is None:
        print(level_text("ERROR", t("No history to compare with.")))
        return
    flavour, match = best
    dates = dict(lines[flavour])
    tree = _tree(repos[flavour], match.commit)
    residual = sorted(p for p, b in client.items() if p in tree and tree[p] != b)
    histories = {f: it.parse_raw_log(git_raw_log(repo, residual) or "") if residual else {}
                 for f, repo in repos.items()}
    verdict = it.core_identity(client, flavour, match.commit, tree, histories)
    print(render_table(["Flavour", "Commit", "Differing", "Patched", "Client-only"],
                       [[verdict.flavour, f"{verdict.commit[:12]} ({dates[verdict.commit]})",
                         str(len(verdict.differing)), str(len(verdict.patched)),
                         str(len(verdict.client_only))]]))
    severity = "high" if verdict.flavour in ("patched", "unidentified") else "info"
    found = [_finding(
        "intake-core", severity, "the Odoo core",
        f"The core is {verdict.flavour} at {verdict.commit[:12]} ({dates[verdict.commit]}): "
        f"{len(verdict.differing)} file(s) differ from that commit, {len(verdict.patched)} match "
        f"no history, {len(verdict.client_only)} are the client's own.",
        {"flavour": verdict.flavour, "closest_flavour": flavour, "commit": verdict.commit,
         "date": dates[verdict.commit], "differing": list(verdict.differing),
         "patched": list(verdict.patched), "client_only": list(verdict.client_only)},
        "git blob ids of the client's core vs git ls-tree of sampled, then nearby, commits of "
        "official Odoo and OCB; differing files looked up in both histories (merges included)",
        "build the source from this core" if not verdict.patched else
        "decide whether to build from this commit and carry the patches")]
    core = it.Core(flavour, verdict.commit) if verdict.flavour in it.FLAVOURS else None
    _record(env, _replace(record, core=core), found, {
        "intake-core-files.tsv": [["path", "state"],
                                  *[[p, "patched" if p in verdict.patched else "other version"]
                                    for p in verdict.differing],
                                  *[[p, "client-only"] for p in verdict.client_only]]})


def unpack_filestore(env: MigrationEnv) -> None:
    record = _current(env)
    if record is None:
        return
    archive = Path(ask_text("Client filestore archive (.tar/.tar.gz)", required=True)).expanduser()
    target = env.data_dir / "filestore" / record.reference_database
    if not archive.is_file():
        print(level_text("ERROR", tf("Cannot read {}.", str(archive))))
        return
    if target.exists():
        print(level_text("ERROR", tf("{} already exists; it is not replaced.", str(target))))
        return
    apply_if_confirmed(planners.plan_unpack_filestore(env, archive, record.reference_database))


def build_source(env: MigrationEnv) -> None:
    record = _current(env)
    if record is None or record.core is None:
        print(level_text("INFO", t("Identify the client's core first.")))
        return
    apply_if_confirmed(planners.plan_seed_environment(env, exists=lambda p: Path(p).exists()))


def copy_reference(env: MigrationEnv) -> None:
    record = _current(env)
    if record is None:
        return
    copy = ask_text("Working copy database", f"{record.reference_database.removesuffix('_original')}_test")
    if not DB_NAME_RE.fullmatch(copy) or copy == record.reference_database:
        print(level_text("ERROR", tf("Invalid database name: {}", copy)))
        return
    if _database_exists(env, copy) is not False:
        print(level_text("ERROR", tf("Database {} exists (or cannot be checked); it is not "
                                     "replaced.", copy)))
        return
    if confirm_with_phrase(tf("{} will be created as a copy of {}. Neutralise it before "
                              "starting Odoo on it.", copy, record.reference_database), "COPY"):
        apply_if_confirmed(planners.plan_copy_database(env, record.reference_database, copy))


def _read_tsv(env: MigrationEnv, name: str) -> list[list[str]]:
    text = read_text(str(env.findings_data_dir / name)) or ""
    return [line.split("\t") for line in text.splitlines()[1:] if line.strip()]


def survey_outbound(env: MigrationEnv) -> None:
    """What the reference can act on, read as its owner, recorded as findings."""
    record = _current(env)
    if record is None:
        return
    ref = record.reference_database
    armed = armed_state(ref, env.db_host, env.db_port, env.db_user)
    mail = mail_state(ref, env.db_host, env.db_port, env.db_user)
    if armed is None or mail is None:
        print(level_text("ERROR", t("Could not tell what the reference can act on; nothing "
                                    "recorded.")))
        return
    rows: dict[str, list[list[str]]] = {}
    for key, sql in it.SURVEY_SQL.items():
        exists = psql_scalar(f"SELECT to_regclass('{it.SURVEY_TABLES[key]}') IS NOT NULL", ref,
                             env.db_host, env.db_port, env.db_user)
        rows[key] = (psql_rows(sql, ref, env.db_host, env.db_port, env.db_user) or []
                     if exists == "t" else [])
    found = [_finding(f"intake-armed-{a.rule}", neutralise.severity(a.rule), a.rule,
                      f"{a.count} row(s) can act on the outside through '{a.rule}'"
                      f"{': ' + a.sample if a.sample else ''}.",
                      {"rule": a.rule, "rows": a.count, "sample": a.sample},
                      f"odoo-dwg neutralise check --database {ref}",
                      "neutralise every working copy") for a in armed]
    if mail.escaping:
        found.append(_finding("intake-armed-mail", "high", "ir_mail_server",
                              f"{len(mail.escaping)} active mail server(s) point outside.",
                              {"servers": [f"{s.host}:{s.port}" for s in mail.escaping]},
                              f"odoo-dwg mail check --database {ref}", "capture the mail"))
    overdue = it.overdue_crons(rows["crons"])
    if overdue:
        found.append(_finding("intake-crons-overdue", "high", "ir_cron",
                              f"{len(overdue)} active cron(s) are past their next call: every one "
                              "fires at the first start.", {"crons": len(overdue)},
                              "findings/data/intake-crons.tsv", "neutralise before any start"))
    for queue in it.read_mail_queue(rows["mail"]):
        if queue.state == "exception":
            found.append(_finding("intake-mail-failed", "high", "mail_mail",
                                  f"{queue.count} outgoing mail(s) failed, from {queue.first} to "
                                  f"{queue.last}; a retry would send them.",
                                  {"count": queue.count, "first": queue.first, "last": queue.last},
                                  "select state, count(*) from mail_mail group by 1",
                                  "ask the client whether to purge them before any working SMTP"))
    _record(env, record, found, {
        "intake-crons.tsv": [["cron", "every", "next_call", "days_overdue"], *rows["crons"]],
        "intake-queue.tsv": [["channel", "state", "jobs"], *rows["queue"]],
        "intake-mail-queue.tsv": [["state", "mails", "first", "last"], *rows["mail"]],
        "intake-armed.tsv": [["rule", "severity", "rows", "sample"],
                             *[[a.rule, neutralise.severity(a.rule), str(a.count), a.sample]
                               for a in armed]],
    })


def _installed_origins(env: MigrationEnv, record: it.IntakeRecord) -> dict[str, tuple[str, str]]:
    remotes = {row[0]: row[1] for row in _read_tsv(env, "intake-repos.tsv") if len(row) > 1}
    prefix = f"{record.core_dir}/" if record.core_dir else ""
    core = {f"{prefix}odoo/addons", f"{prefix}addons"}
    out = {}
    for row in _read_tsv(env, "intake-installed.tsv"):
        if len(row) < 2 or row[1] == "MISSING":
            continue
        origin = it.module_origin(row[1], core, remotes)
        out[row[0]] = (origin, it.oca_repo(remotes.get(row[1], "")) or "")
    return out


def _step_modules(env: MigrationEnv, step: str, repos: set[str] | None) -> dict[str, str]:
    """``{module: "core" | repo}`` at a step: the core first, then OCA trees."""
    core = env.openupgrade_clone_dir(step) if env.uses_legacy_layout(step) \
        else env.odoo_clone_dir(step)
    found = {m: "core" for _d, m, _f in scan_manifests(core, ["addons", "odoo/addons"])}
    trees = env.repos_dir / "oca-trees"
    for tree in sorted(trees.glob(f"*-{step}")):
        repo = tree.name[: -len(step) - 1]
        if tree.is_dir() and (repos is None or repo in repos):
            for module in tree_modules(tree):
                found.setdefault(module, repo)
    return found


def check_availability(env: MigrationEnv) -> None:
    """Each installed Odoo/OCA module at each step; all of OCA where gaps remain."""
    record = _current(env)
    if record is None:
        return
    installed = _installed_origins(env, record)
    if not installed:
        print(level_text("INFO", t("Classify the client's add-ons archive first.")))
        return
    steps = env.chain()
    client_repos = {repo for origin, repo in installed.values() if origin == "oca" and repo}
    missing = {r: [v for v in steps if not planners.oca_tree_dir(env, r, v).exists()
                   and not Path(f"{planners.oca_tree_dir(env, r, v)}.absent").exists()]
               for r in client_repos}
    missing = {r: v for r, v in missing.items() if v}
    if missing and not apply_if_confirmed(planners.plan_oca_trees(env, missing)):
        return
    modules = sorted(m for m, (origin, _r) in installed.items() if origin != "custom")
    fates, unread = preflight.chain_fates(modules, [(v, env.apriori_file(v)) for v in steps])
    if unread:
        print(level_text("WARN", tf("No apriori.py read for: {}", ", ".join(unread))))
    found = {v: _step_modules(env, v, client_repos) for v in steps}
    rows = it.availability(installed, fates, steps, found)
    gap_steps = sorted({steps[i] for r in rows for i in r.gaps})
    if gap_steps:
        listing = github_org_repos("OCA")
        if listing is None:
            print(level_text("WARN", t("Could not list OCA's repositories: gaps are provisional.")))
        else:
            wanted = {r: [v for v in gap_steps if not planners.oca_tree_dir(env, r, v).exists()
                          and not Path(f"{planners.oca_tree_dir(env, r, v)}.absent").exists()]
                      for r in listing}
            wanted = {r: v for r, v in wanted.items() if v}
            print(level_text("INFO", tf("{} OCA tree(s) to fetch for the steps with gaps: {}",
                                        str(sum(len(v) for v in wanted.values())),
                                        ", ".join(gap_steps))))
            if wanted and not apply_if_confirmed(planners.plan_oca_trees(env, wanted)):
                return
            found = {v: _step_modules(env, v, None) for v in steps}
            rows = it.availability(installed, fates, steps, found)
    gaps = [r for r in rows if r.gaps]
    moved = [r for r in rows if r.moved]
    port = [r.module for r in rows if r.origin == "custom"]
    found_list = [_finding(
        "intake-availability", "info", "installed modules along the chain",
        f"{len(rows)} installed modules: {len(gaps)} with gaps, {len(moved)} moved repository, "
        f"{len(port)} custom to port.", {"gaps": len(gaps), "moved": len(moved),
                                        "custom": len(port)},
        "findings/data/intake-availability.tsv", "decide per gap: replace, drop or port")]
    if gaps:
        found_list.append(_finding(
            "intake-gaps", "high", "OCA modules",
            "Installed modules whose code is found in no OCA repository at some step.",
            {r.module: [steps[i] for i in r.gaps] for r in gaps},
            "findings/data/intake-availability.tsv (MISSING)",
            "per module: replace, uninstall before the chain, or port the missing step"))
    if moved:
        found_list.append(_finding(
            "intake-moved", "info", "OCA modules", "Modules found in another OCA repository at "
            "a later step: the chain must clone that repository.",
            {r.module: sorted({w for w in r.where if w not in ("core", "MISSING")})
             for r in moved}, "findings/data/intake-availability.tsv",
            "add those repositories to the environment"))
    _record(env, record, found_list, {"intake-availability.tsv": [
        ["module", "origin", "source_repo", "merged_at", *steps],
        *[[r.module, r.origin, r.source_repo, r.merged_at, *r.where] for r in rows]]})


def scan_custom(env: MigrationEnv) -> None:
    """The client's own installed modules, scanned for network calls — once the
    scanner has shown it matches what it looks for."""
    record = _current(env)
    if record is None:
        return
    broken = it.scanner_self_test()
    if broken:
        print(level_text("ERROR", tf("The scanner fails its own control for: {}. No result is "
                                     "reported.", ", ".join(broken))))
        return
    installed = _installed_origins(env, record)
    loads = {row[0]: row[1] for row in _read_tsv(env, "intake-installed.tsv") if len(row) > 1}
    archive = env.root / record.archive_root
    hits: list[list[str]] = []
    files = 0
    custom = sorted(m for m, (origin, _r) in installed.items() if origin == "custom")
    for module in custom:
        base = archive / loads[module] / module
        for path in sorted(base.rglob("*.py")):
            rel = str(path.relative_to(base))
            if it.scan_skipped(rel):
                continue
            files += 1
            for number, pattern, line in it.scan_source(read_text(str(path)) or ""):
                hits.append([module, rel, str(number), pattern, line])
    found = [_finding(
        "intake-custom-scan", "info", "custom modules",
        f"Scanned {len(custom)} custom module(s), {files} Python file(s), the scanner passing its "
        f"control first: {len(hits)} line(s) read as network calls or processes.",
        {"modules": len(custom), "files": files, "hits": len(hits)},
        "findings/data/intake-custom-scan.tsv",
        "read every hit; none found means no pattern matched, not that the code is safe")]
    for module in sorted({h[0] for h in hits}):
        mine = [h for h in hits if h[0] == module]
        found.append(_finding(
            f"intake-network-{module.replace('_', '-').lower()}", "high", module,
            f"{len(mine)} line(s) of {module} read as network calls or processes.",
            {"hits": [f"{h[1]}:{h[2]} {h[3]}" for h in mine[:20]]},
            "findings/data/intake-custom-scan.tsv", "read them; neutralise what they reach"))
    _record(env, record, found, {"intake-custom-scan.tsv": [
        ["module", "file", "line", "pattern", "text"], *hits]})


def show_intake(env: MigrationEnv) -> None:
    record = _current(env)
    if record is not None:
        print(it.dump_intake(record))


def intake_menu(env: MigrationEnv) -> None:
    steps = {
        "Restore the client's dump": restore_dump,
        "Create the read-only role": create_reader,
        "Unpack the client's add-ons archive": unpack_archive,
        "Classify the add-ons archive": classify_archive,
        "Identify the client's core": identify_core,
        "Unpack the client's filestore": unpack_filestore,
        "Build the client's source": build_source,
        "Copy the reference to a working database": copy_reference,
        "Survey what the copy can act on": survey_outbound,
        "Check each installed module along the chain": check_availability,
        "Scan the client's own code for network calls": scan_custom,
        "Show the intake": show_intake,
    }
    while True:
        action = choose(tf("\nTake in a client copy ({} → {})", env.source, env.target),
                        list(steps) + ["Back"])
        if action in ("", "Back"):
            return
        steps[action](env)
        env.intake = load_intake(env)
