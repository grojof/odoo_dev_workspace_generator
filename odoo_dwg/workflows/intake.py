"""Taking in a client copy, from the menu.

Each step changes the host through a previewed plan, then records what it found
— ``intake.json``, data tables under ``findings/data/`` and findings in the
ledger — through a second previewed plan. Findings are recorded ``internal`` and
in English: the client-facing text is the operator's to write.
"""

from __future__ import annotations

import csv
import hashlib
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
from ..models import (
    DB_NAME_RE,
    LEGACY_LAYOUT_MAX_MAJOR,
    MODULE_NAME_RE,
    Command,
    MigrationEnv,
    odoo_major,
)
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
            tables: dict[str, list[list[str]]], texts: dict[str, str] | None = None) -> None:
    """Write the record, the tables (and any other files) and the new findings, through
    one previewed plan."""
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
    for name, text in (texts or {}).items():
        commands += write_text_file_command(env.findings_data_dir / name, text)
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


def _neutral(env: MigrationEnv, database: str) -> bool:
    armed = armed_state(database, env.db_host, env.db_port, env.db_user)
    mail = mail_state(database, env.db_host, env.db_port, env.db_user)
    if armed is None or mail is None:
        print(level_text("ERROR", tf("Could not tell whether {} is neutralised.", database)))
        return False
    if armed or mail.escaping:
        print(level_text("ERROR", tf("{} can still act on the outside: run 'Neutralise a "
                                     "database' on it first.", database)))
        return False
    return True


def _snapshot(env: MigrationEnv, database: str) -> tuple | None:
    """Exact rows per table, columns and installed modules; None if unreadable."""
    reads = [psql_rows(sql, database, env.db_host, env.db_port, env.db_user)
             for sql in (it.UNINSTALL_ROWS_SQL, it.UNINSTALL_COLUMNS_SQL,
                         it.UNINSTALL_INSTALLED_SQL)]
    if any(r is None for r in reads):
        return None
    rows, columns, installed = reads
    return (it.parse_counts(rows), it.parse_columns(columns),
            {r[0] for r in installed if r})


def _compare_uninstall(env: MigrationEnv, copy: str, scratch: str,
                       modules: list[str]) -> tuple[list, list[str]] | None:
    before, after = _snapshot(env, copy), _snapshot(env, scratch)
    if before is None or after is None:
        return None
    along = it.taken_along(modules, before[2], after[2])
    q = {"db": copy, "host": env.db_host, "port": env.db_port, "user": env.db_user}
    owned = psql_rows(it.owned_rows_sql(modules + along), **q)
    transient = psql_rows(it.UNINSTALL_TRANSIENT_SQL, **q)
    related = psql_rows(it.UNINSTALL_RELATED_SQL, **q)
    gone = sorted(c for c in before[1] - after[1] if c[0] in after[0])
    values = psql_rows(it.column_values_sql(gone), **q) if gone else []
    if None in (owned, transient, related, values):
        return None
    changes = it.diff_uninstall(
        before[0], after[0], before[1], after[1], it.parse_counts(owned),
        {r[0] for r in transient if r}, {(r[0], r[1]) for r in related if len(r) > 1},
        {(r[0], r[1]): int(r[2]) for r in values if len(r) > 2 and r[2].isdigit()})
    return changes, along


def rehearse_uninstall(env: MigrationEnv) -> None:
    """Uninstall modules on a throwaway clone of a neutralised copy, and name every
    difference it made to the client's data."""
    record = _current(env)
    if record is None:
        return
    ref = record.reference_database
    copy = ask_text("Neutralised working copy", f"{ref.removesuffix('_original')}_test")
    if not DB_NAME_RE.fullmatch(copy) or copy == ref:
        print(level_text("ERROR", tf("Not a working copy: {}", copy)))
        return
    if _database_exists(env, copy) is not True or not _neutral(env, copy):
        return
    modules = sorted({m.strip() for m in ask_text("Modules to uninstall (comma-separated)",
                                                   required=True).split(",") if m.strip()})
    bad = [m for m in modules if not MODULE_NAME_RE.fullmatch(m)]
    installed = psql_rows(it.UNINSTALL_INSTALLED_SQL, copy, env.db_host, env.db_port,
                          env.db_user)
    if bad or installed is None:
        print(level_text("ERROR", tf("Invalid module names: {}", ", ".join(bad) or "?")))
        return
    missing = sorted(set(modules) - {r[0] for r in installed if r})
    if missing:
        print(level_text("ERROR", tf("Not installed in {}: {}", copy, ", ".join(missing))))
        return
    dependents = psql_rows(it.dependents_sql(modules), copy, env.db_host, env.db_port,
                           env.db_user)
    if dependents is None:
        print(level_text("ERROR", tf("Could not read database {}.", copy)))
        return
    if dependents:
        print(level_text("WARN", tf("Uninstalling these also uninstalls: {}",
                                    ", ".join(r[0] for r in dependents if r))))
    scratch = ask_text("Throwaway database", f"{copy}_uninstall")
    if not DB_NAME_RE.fullmatch(scratch) or scratch in (ref, copy):
        print(level_text("ERROR", tf("Invalid database name: {}", scratch)))
        return
    if _database_exists(env, scratch) is not False:
        print(level_text("ERROR", tf("Database {} exists (or cannot be checked); it is not "
                                     "replaced.", scratch)))
        return
    if not confirm_with_phrase(tf("{} will be created from {}, and {} uninstalled on it. {} "
                                  "itself is not modified.", scratch, copy,
                                  ", ".join(modules), copy), "REHEARSE"):
        return
    if not apply_if_confirmed(planners.plan_uninstall_rehearsal(env, copy, scratch, modules)):
        return
    record_uninstall(env, record, copy, scratch, modules)


def _next_run_id(env: MigrationEnv, prefix: str) -> str:
    """A fresh id per rehearsal: the same modules rehearsed again are a new run,
    and an id once withdrawn is never reused."""
    text = read_text(str(env.findings_ledger))
    taken = set()
    if text is not None:
        ledger = fl.parse_ledger(text)
        taken = {f.id for f in ledger.findings} | {c.withdrawn for c in ledger.corrections}
    n = 1
    while f"{prefix}-{n}" in taken:
        n += 1
    return f"{prefix}-{n}"


def record_uninstall(env: MigrationEnv, record: it.IntakeRecord, copy: str, scratch: str,
                     modules: list[str]) -> None:
    """Compare a working copy with its uninstalled clone, and record the result."""
    compared = _compare_uninstall(env, copy, scratch, modules)
    if compared is None:
        print(level_text("ERROR", t("Could not compare the two databases; nothing recorded.")))
        return
    changes, along = compared
    by_kind: dict[str, int] = {}
    for c in changes:
        by_kind[c.kind] = by_kind.get(c.kind, 0) + (c.before - c.after if not c.column
                                                    else c.before)
    lost = [c for c in changes if c.kind == "data lost"]
    print(render_table(["Table", "Column", "Kind", "Before", "After", "Owned"],
                       [[c.table, c.column, c.kind, str(c.before), str(c.after), str(c.owned)]
                        for c in changes if c.kind in ("data lost", "recomputed", "grew")]
                       or [["-", "-", t("no client data lost"), "", "", ""]]))
    if along:
        print(level_text("WARN", tf("The uninstall took along: {}", ", ".join(along))))
    fid = _next_run_id(
        env, f"uninstall-rehearsal-{hashlib.sha1(','.join(modules).encode()).hexdigest()[:8]}")
    name = f"{fid}.tsv"
    lost_text = "; ".join(f"{c.table}{'.' + c.column if c.column else ''} "
                          f"({c.before - c.after if not c.column else c.before} rows)"
                          for c in lost)
    found = [_finding(
        fid, "high" if lost else "info", ", ".join(modules),
        (f"Uninstalling on a copy loses client data: {lost_text}." if lost else
         "Uninstalling on a copy lost no client data: "
         + ", ".join(f"{n} {k}" for k, n in sorted(by_kind.items())) + ".")
        + (f" It took along: {', '.join(along)}." if along else ""),
        {"modules": modules, "taken_along": along, "copy": copy, "throwaway": scratch,
         "rows_by_kind": by_kind, "data_lost": [c.table + ("." + c.column if c.column else "")
                                                for c in lost]},
        f"findings/data/{name}; row counts and columns of {copy} against {scratch}",
        "review the tables named data lost before uninstalling" if lost
        else "uninstall these modules before the chain")]
    _record(env, record, found, {name: [["table", "column", "kind", "before", "after", "owned"],
                                        *[[c.table, c.column, c.kind, str(c.before),
                                           str(c.after), str(c.owned)] for c in changes]]})
    print(level_text("INFO", tf("{} is left in place for inspection; drop it when done.",
                                scratch)))


def _audit_module_rows(env: MigrationEnv, db: str, modules: list[str], since: str,
                       target: str | None) -> list[it.AuditRow] | None:
    """Every piece of evidence about the modules, read from ``db`` (and ``target``)."""
    q = {"host": env.db_host, "port": env.db_port, "user": env.db_user}
    reads = [psql_rows(sql, db, **q) for sql in (
        it.audit_models_sql(modules), it.audit_fields_sql(modules), it.audit_reports_sql(modules),
        it.audit_dependents_sql(modules), it.UNINSTALL_COLUMNS_SQL)]
    if any(r is None for r in reads):
        return None
    models, fields, reports, dependents, columns = reads
    cols = it.parse_columns(columns)
    target_cols = (it.parse_columns(psql_rows(it.UNINSTALL_COLUMNS_SQL, target, **q) or [])
                   if target else set())
    rows: list[it.AuditRow] = []

    def one(sql: str, database: str = db) -> list[str]:
        got = psql_rows(sql, database, **q)
        return got[0] if got else ["?", "", ""]

    def survived(table: str, column: str, sql: str) -> str:
        if not target:
            return ""
        if (table, column) not in target_cols:
            return "not in the migrated database"
        return f"migrated: {one(sql, target)[0]}"

    for module, dependent in (r for r in dependents if len(r) > 1):
        rows.append(it.AuditRow(module, "dependent", dependent))
    for module, model, transient in (r for r in models if len(r) > 2):
        table = it.model_table(model)
        if transient == "t":
            seq = psql_rows(f"SELECT last_value, is_called FROM {table}_id_seq", db, **q) or []
            opened = seq[0][0] if seq and seq[0][1] == "t" else "0"
            rows.append(it.AuditRow(module, "wizard", model, opened, note="times opened, ever"))
        elif (table, "id") in cols:
            dated = (table, "write_date") in cols
            total, recent, last = one(it.audit_table_sql(table, since, dated))
            rows.append(it.AuditRow(module, "model", model, total, recent, last,
                                    survived(table, "id", it.audit_table_sql(table, since, False))))
    # A wizard's own fields and links hold only what its vacuumed rows held: its use is
    # the times it was opened, recorded above, and listing them only adds zeros.
    transient = {r[1] for r in models if len(r) > 2 and r[2] == "t"}
    for module, model, name, ttype, store, related, relation in (r for r in fields if len(r) > 6):
        table = it.model_table(model)
        if model in transient or store != "t" or (table, name) not in cols and ttype != "many2many":
            continue
        if ttype == "many2many":
            if relation and (relation, "id") not in cols and any(t == relation for t, _ in cols):
                total = one(f'SELECT count(*), \'\', \'\' FROM public."{relation}"')[0]
                rows.append(it.AuditRow(module, "m2m", f"{model}.{name}", total, note=relation))
            continue
        if related:
            rows.append(it.AuditRow(module, "related", f"{model}.{name}", note=related))
            continue
        dated = (table, "write_date") in cols
        total, recent, last = one(it.audit_field_sql(table, name, since, dated))
        rows.append(it.AuditRow(module, "field", f"{model}.{name}", total, recent, last,
                                survived(table, name,
                                         it.audit_field_sql(table, name, since, False))))
    for module, report, model, menu, namespace, printed in (r for r in reports if len(r) > 5):
        prefix = it.print_name_prefix(printed)
        total = recent = ""
        if prefix:
            like = prefix.replace("'", "''").replace("%", "").replace("_", "\\_")
            total, recent, _last = one(
                f"SELECT count(*), count(*) FILTER (WHERE create_date >= '{since}'), '' "
                f"FROM ir_attachment WHERE name LIKE '{like}%'")
        notes = [f"on {model}", "in the Print menu" if menu == "t" else "not in the Print menu"]
        if namespace and namespace != module:
            notes.append(f"registered as {namespace}.*: updating {namespace} can remove it")
        rows.append(it.AuditRow(module, "document", report, total, recent, note="; ".join(notes)))
    return rows


def audit_own_modules(env: MigrationEnv) -> None:
    """What each of the client's own modules stores, who uses it, and since when."""
    record = _current(env)
    if record is None:
        return
    own = sorted(m for m, (origin, _repo) in _installed_origins(env, record).items()
                 if origin == "custom")
    extra = ask_text("Other modules to audit (comma-separated, optional)", "", required=False)
    modules = sorted(set(own) | {m.strip() for m in extra.split(",") if m.strip()})
    bad = [m for m in modules if not MODULE_NAME_RE.fullmatch(m)]
    if not modules or bad:
        print(level_text("ERROR", tf("Invalid module names: {}", ", ".join(bad) or "?")))
        return
    since = ask_text("Count use since (YYYY-MM-DD)", f"{date.today().year - 1}-01-01")
    target = ask_text("Migrated database to check survival in (optional)", "", required=False)
    log_path = ask_text("Web access log to count prints from (optional)", "", required=False)
    if not it._DATE_RE.fullmatch(since) or target and not DB_NAME_RE.fullmatch(target):
        print(level_text("ERROR", t("Not a date, or not a database name.")))
        return
    rows = _audit_module_rows(env, record.reference_database, modules, since, target or None)
    if rows is None:
        print(level_text("ERROR", tf("Could not read database {}; nothing recorded.",
                                     record.reference_database)))
        return
    if log_path:
        text = read_text(str(Path(log_path).expanduser()))
        if text is None:
            print(level_text("ERROR", tf("Could not read {}; nothing recorded.", log_path)))
            return
        prints = it.report_prints(text, since)
        rows = [replace(r, since=str(prints.get(r.subject, (0, 0))[0]),
                        note=r.note + f"; prints since {since} in the log: "
                        f"{prints.get(r.subject, (0, 0))[0]}"
                        + (f" (+{prints[r.subject][1]} undated)"
                           if prints.get(r.subject, (0, 0))[1] else ""))
                if r.kind == "document" else r for r in rows]
    published = {}
    for tree in sorted((env.repos_dir / "oca-trees").glob(f"*-{env.target}")):
        for module in tree_modules(tree) & set(modules):
            published.setdefault(module, tree.name.removesuffix(f"-{env.target}"))
    labels = {m: it.audit_label([r for r in rows if r.module == m], since) for m in modules}
    summary = [[m, labels[m], published.get(m, ""),
                ", ".join(r.subject for r in rows if r.module == m and r.kind == "dependent")]
               for m in modules]
    print(render_table(["Module", "Evidence", f"OCA {env.target}", "Required by"], summary))
    counts: dict[str, int] = {}
    for label in labels.values():
        key = label.split(" since")[0].replace(",", "")
        counts[key] = counts.get(key, 0) + 1
    found = [_finding(
        _next_run_id(env, "own-modules-audit"), "info", f"{len(modules)} client-own modules",
        f"Evidence per module since {since}: " + ", ".join(f"{n} {k}" for k, n in
                                                            sorted(counts.items())) + ".",
        {"since": since, "labels": labels, "published_by_oca": published,
         "migrated_database": target or "", "access_log": bool(log_path)},
        "findings/data/own-modules-audit.tsv, own-modules-summary.tsv",
        "decide per module from its code: drop, replace or port")]
    _record(env, record, found, {
        "own-modules-summary.tsv": [["module", "evidence", f"oca_{env.target}", "required_by"],
                                    *summary],
        "own-modules-audit.tsv": [["module", "kind", "subject", "total", f"since_{since}", "last",
                                   "note"],
                                  *[[r.module, r.kind, r.subject, r.total, r.since, r.last, r.note]
                                    for r in rows]]})


def find_bank_duplicates(env: MigrationEnv) -> None:
    """Bank statement lines imported twice, proven by the bank's own balances.

    Up to 13.0 an unreconciled line has no entry; OpenUpgrade's 14.0 step gives every
    one an entry, so a statement imported twice becomes movements that never happened.
    Reads the reference only, and deletes nothing: it writes a guarded SQL file the
    operator may put in the first step's pre hook, on a working copy."""
    record = _current(env)
    if record is None:
        return
    if odoo_major(env.source) > LEGACY_LAYOUT_MAX_MAJOR:
        print(level_text("INFO", tf(
            "From 14.0 every statement line already has its entry; this step is for a source up "
            "to 13.0, and the source is {}.", env.source)))
        return
    ref = record.reference_database
    q = {"host": env.db_host, "port": env.db_port, "user": env.db_user}
    copies_rows = psql_rows(it.BANK_DUPLICATES_SQL, ref, **q)
    stats = psql_rows(it.BANK_LINES_STATS_SQL, ref, **q)
    locked_rows = psql_rows(it.BANK_LOCKED_SQL, ref, **q)
    if copies_rows is None or locked_rows is None or not stats or len(stats[0]) < 5:
        print(level_text("ERROR", tf("Could not read database {}; nothing recorded.", ref)))
        return
    statements, matching, lines, unreconciled, after_lock = (int(v) for v in stats[0][:5])
    copies = it.parse_bank_copies(copies_rows)
    duplicates = [c for c in copies if c.kind == "duplicate"]
    twice = [c for c in copies if c.kind == "reconciled twice"]
    net = sum(float(c.amount) for c in duplicates)
    locked = it.parse_locked_lines(locked_rows, {c.line for c in duplicates})
    kept = [x for x in locked if x.kept]
    behind = [x for x in locked if not x.kept]
    print(render_table(["", ""], [
        [t("Statements matching the bank's balances"), f"{matching} / {statements}"],
        [t("Unreconciled lines"), f"{unreconciled} / {lines}"],
        [t("Of them, certain duplicates"), f"{len(duplicates)} ({net:.2f})"],
        [t("Movements reconciled more than once"), str(len(twice))],
        [t("Unreconciled lines after the lock date"), str(after_lock)],
        [t("Closed-period lines that match an open item (kept)"), str(len(kept))],
        [t("Closed-period lines the accountant may leave behind"), str(len(behind))],
    ]))
    hook = env.hooks_dir / f"{env.chain()[0]}-pre.sql"
    found = [_finding(
        _next_run_id(env, "bank-lines-imported-twice"),
        "high" if duplicates or twice else "info", "account_bank_statement_line",
        f"{len(duplicates)} unreconciled statement line(s) are certain duplicates (net {net:.2f}), "
        f"{len(twice)} movement(s) were reconciled more than once; {matching} of {statements} "
        f"statement(s) match the bank's balances. Of {unreconciled} unreconciled line(s), "
        f"{after_lock} fall after the lock date. OpenUpgrade 14.0 gives every unreconciled line "
        "an entry, so a duplicate would become a bank movement that never happened. Of the "
        f"closed-period ones, {len(kept)} match an open item of the same partner (kept) and "
        f"{len(behind)} could be left behind, if the client's accountant decides so.",
        {"statements": statements, "statements_matching_file": matching, "lines": lines,
         "unreconciled": unreconciled, "unreconciled_after_lock": after_lock,
         "duplicates": len(duplicates), "duplicates_net": round(net, 2),
         "reconciled_twice": [[c.line, c.kept, c.journal, c.date, c.amount] for c in twice],
         "closed_period_kept": len(kept), "closed_period_to_leave": len(behind)},
        "findings/data/bank-duplicate-lines.tsv",
        f"review, then put findings/data/bank-duplicate-lines.sql in {hook} (working copy only); "
        "the client's accountant decides on movements reconciled more than once, and whether "
        "bank-locked-unreconciled.sql goes in the hook too; re-run on the final copy")]
    _record(env, record, found, {
        "bank-duplicate-lines.tsv": [
            ["kind", "statement_line_id", "statement_id", "journal", "date", "amount", "kept_line_id"],
            *[[c.kind, str(c.line), str(c.statement), c.journal, c.date, c.amount, str(c.kept)]
              for c in copies]],
        "bank-locked-unreconciled.tsv": [
            ["statement_line_id", "journal", "date", "amount", "label", "reference", "partner",
             "note", "statement_id", "kept_matches_open_item"],
            *[[str(x.line), x.journal, x.date, x.amount, x.label, x.ref, x.partner, x.note,
               str(x.statement), "yes" if x.kept else ""] for x in locked]]},
        {"bank-duplicate-lines.sql": it.bank_duplicates_sql(copies),
         "bank-locked-unreconciled.sql": it.locked_lines_sql(locked)})


def find_journal_codes(env: MigrationEnv) -> None:
    """Journal codes the target refuses: shared in a company, or confusable.

    From 15.0 each step drops ``unique (company_id, code)`` and adds it again; with a
    shared code it only logs that it could not, and the migrated database keeps no
    constraint. Reads the reference only; the operator's codes in the table are kept."""
    record = _current(env)
    if record is None:
        return
    rows = psql_rows(it.JOURNAL_CODES_SQL, record.reference_database, host=env.db_host,
                     port=env.db_port, user=env.db_user)
    if rows is None:
        print(level_text("ERROR", tf("Could not read database {}; nothing recorded.",
                                     record.reference_database)))
        return
    table = "journal-codes.tsv"
    edits = {int(r[1]): r[-1] for r in _read_tsv(env, table)
             if len(r) >= 10 and r[1].isdigit() and r[-1].strip()}
    plan, problems = it.journal_code_plan(rows, edits)
    if problems:
        print(level_text("ERROR", tf("Fix these codes in findings/data/{} and run again: {}",
                                     table, "; ".join(problems))))
        return
    print(render_table(["Id", "Code", "Entries", "Group", "Proposed", "Journal"],
                       [[str(j.id), repr(j.code), str(j.entries), j.group, j.proposed or "(keeps)",
                         j.name[:40]] for j in plan]))
    renamed = [j for j in plan if j.proposed]
    shared = [j for j in plan if j.group == "shared"]
    hook = env.hooks_dir / f"{env.chain()[0]}-pre.sql"
    found = [_finding(
        _next_run_id(env, "journal-codes"), "high" if shared else ("low" if plan else "info"),
        "account_journal",
        f"{len(renamed)} journal(s) to rename: {len(shared)} journal(s) share a code in their "
        f"company, {len(plan) - len(shared)} have codes that differ only by case or spaces. From "
        "15.0 the migration cannot add unique (company_id, code) and only logs it.",
        {"renamed": {str(j.id): [j.code, j.proposed] for j in renamed},
         "operator_codes": len([j for j in renamed if j.id in edits])},
        f"findings/data/{table}",
        f"edit the proposed codes in findings/data/{table} if needed, re-run, then put "
        f"findings/data/journal-codes.sql in {hook} (working copy only)")]
    _record(env, record, found, {table: [
        ["company", "journal_id", "name", "type", "active", "entries", "last_entry", "group", "code",
         "proposed"],
        *[[str(j.company), str(j.id), j.name, j.type, "yes" if j.active else "no", str(j.entries),
           j.last, j.group, j.code, j.proposed] for j in plan]]},
        {"journal-codes.sql": it.journal_codes_sql(plan)})


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
        "Rehearse uninstalling modules on a copy": rehearse_uninstall,
        "Audit the client's own modules": audit_own_modules,
        "Find bank statement lines imported twice": find_bank_duplicates,
        "Find journal codes the target refuses": find_journal_codes,
        "Show the intake": show_intake,
    }
    while True:
        action = choose(tf("\nTake in a client copy ({} → {})", env.source, env.target),
                        list(steps) + ["Back"])
        if action in ("", "Back"):
            return
        steps[action](env)
        env.intake = load_intake(env)
