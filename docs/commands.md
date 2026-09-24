---
type: reference
title: "Command reference"
description: "Every CLI invocation, menu action, confirmation phrase, and environment variable."
audience: [developer, operator]
updated: 2026-09-20
---

# Command reference

The tool is one executable with an interactive menu and three direct subcommands. Every host-mutating
action assembles a command **plan**, previews it, and runs it only after confirmation; destructive actions
additionally require typing an exact phrase.

## Invocation

| Command | What it opens |
|---|---|
| `python3 -m odoo_dwg` | Interactive top-level menu |
| `python3 -m odoo_dwg workspace` | Workspace section directly |
| `python3 -m odoo_dwg provision` | Provisioning section directly |
| `python3 -m odoo_dwg migrate` | Migration mode directly |
| `odoo-dwg …` | Console-script equivalent (after `pip install -e .`) |

`--lang` and `-v` work before or after the subcommand:

| Flag | Effect |
|---|---|
| `--lang {en,es}` | UI language, instead of the prompt (also `ODWG_LANG`) |
| `-v`, `--verbose` | Stream every line a plan's commands print (also `ODWG_VERBOSE=1`) |
| `--version` | Print the version and exit (top-level only, not after a subcommand) |
| `-h`, `--help` | Usage for the tool or for a subcommand |

## How a plan reports while it runs

A plan is always previewed and confirmed first. While it runs:

- **By default** each step is one line — `[3/12] Clone Odoo 18.0 … [OK]` — plus any line a step printed that
  mentions a warning, a deprecation, an error or a failure — at most ten such lines per step.
- **A step that fails** prints the end of its output (the last 40 lines), then the plan stops.
- **With `--verbose`** every line appears live, which is what you want while watching a long `git clone` or
  `pip install`.

## Environment variables

| Variable | Effect |
|---|---|
| `ODWG_LANG=en\|es` | UI language without the startup prompt (artifacts are always English) |
| `ODWG_VERBOSE=1` | Stream every line a plan's commands print, same as `--verbose` |
| `NO_COLOR` | Set to anything: never colour the output, whatever the terminal is |
| `FORCE_COLOR` | Set to anything: colour even when the output is not a terminal (ignored when `NO_COLOR` is set) |

## Menus and actions

Every menu shows a numbered list; `0` (or `Back`/`Cancel`) always returns without acting.

### Workspaces (create / manage)

| Action | Behavior | Guard |
|---|---|---|
| Create a workspace → New (quick) | Interactive minimal profile, then full generation plan | Create-only: refuses to clobber an existing workspace |
| Create a workspace → From a profile file | Same, loading a JSON profile (see [configuration-reference](configuration-reference.md)) | idem |
| Manage → Refresh generated files | Rewrites the generated configs, scripts, `.vscode/*`, `odools.toml`, README and profile from `workspace.json`. Only files that change are written, and each changed file is first kept as `<file>.bak-<date>`. Each venv's interpreter is read from its `pyvenv.cfg`. Addons, venvs, clones and databases are never touched. | Preview + confirm |
| Manage → Regenerate a venv | Removes and rebuilds one instance venv | Phrase `REBUILD` |
| Manage → Refresh shared repos | `git pull --ff-only` on present clones in the shared cache | Preview + confirm |
| Manage → Add a version | Extends an existing workspace with a new Odoo version. It writes files like **Refresh generated files**, and the other versions keep their interpreters. The workspace changes only once the plan has run: a declined or failed plan adds nothing. | Preview + confirm |
| Manage → Capture a database's mail in Mailpit | Deactivates a named database's mail servers **without altering them** and adds one pointing at `127.0.0.1:1025`; deactivates fetchmail; records what it did inside that database. Odoo 12–19, safe to repeat ([egress-control](egress-control.md#a-copied-database-still-mails-out-capture-it)). | Phrase `CAPTURE` |
| Manage → Restore a database's mail configuration | Removes the capture's server and switches back on exactly what the capture switched off, then drops its record. Refuses a database that was never captured. | Phrase `RESTORE` |
| Manage → Check whether a database can mail out | Reads only. Names every active mail server, whether fetchmail is running, and whether a capture is in effect. | — |

### System provisioning (optional; the Ubuntu releases in the [support matrix](support-matrix.md))

| Action | Behavior | Guard |
|---|---|---|
| Check host readiness | Read-only capability table (host release, build deps, PostgreSQL + role + server version + loopback auth, wkhtmltopdf, Node and rtlcss, host `python3`, uv interpreters, OpenSnitch and whether it is hardened, Mailpit) | Never mutates |
| Apply (install what's missing) | Plans installs for missing capabilities. rtlcss (right-to-left languages only), the outbound firewall (OpenSnitch) and the mail capture (Mailpit) are separate opt-ins ([egress-control](egress-control.md)). | Root required; preview + confirm |
| Outbound firewall and mail capture (on/off, uninstall) | Shows both components' state. Turns each off or on (persistent across restarts), or uninstalls it. For OpenSnitch it lists what `apt` removes first and keeps your own rules. ([details](egress-control.md#turning-it-off-or-uninstalling)) | Root required; preview + confirm; phrase `UNINSTALL` to uninstall |

### Migration (OpenUpgrade 12→19)

| Action | Behavior | Guard |
|---|---|---|
| Generate a migration environment | Asks which core the steps from 14.0 run on (official Odoo or OCB; default: the client's), then the chain-scoped host preflight table, then the full plan (clones, uv venvs with `--overrides` repairs, per-step confs, addons layout, checkpointing driver) | MISSING checks require explicit confirmation; preview + confirm |
| Preflight check | Read-only verification: chain tools, PostgreSQL, dump integrity, and — against a named database — version match, installed modules, per-step addons coverage | Never mutates |
| Stage custom modules | Per chain step, copies the previous stage and runs `odoo-module-migrator` on it; then analysis findings, inert `pre-migration.py` scaffolds, and a per-module report | Source dir never modified; phrase `RESTAGE` to replace staged code |
| Clean a migration environment | Removes one `<src>-to-<tgt>` directory; the shared `.repos` cache is a separate opt-in | Phrase `DELETE`; the PostgreSQL DB is never touched |
### Read-only commands (no menu, no prompt, nothing written)

These exist so an answer can be had from a script, from a pipe, or from a second terminal while a
migration runs. Each exits **0** when it found nothing, **1** when it found something, **2** when it could
not tell — and exit 2 is never a clean result.

| Command | Answers |
|---|---|
| `odoo-dwg egress check` | Are the tool's OpenSnitch rules still as it wrote them, and does anything sort ahead of them? |
| `odoo-dwg mail check --database X` | Can mail leave this database? |
| `odoo-dwg migrate report --source A --target B` | The cumulative run report, to stdout (the menu action writes a file; this does not). |
| `odoo-dwg migrate probes --source A --target B --database X` | What became of each rehearsal probe's subject. |
| `odoo-dwg neutralise check --database X` | Can anything in this database still act on the outside? Rule by rule, with the mail verdict. |
| `odoo-dwg migrate findings list --source A --target B` | The findings and their decisions; exit 1 while one is still pending. |
| `odoo-dwg migrate findings show ID --source A --target B` | One finding in full, as the ledger holds it. |
| `odoo-dwg migrate findings validate --source A --target B` | Whether the ledger is one the tool accepts; every problem named. |
| `odoo-dwg migrate findings report --source A --target B [--kind client\|extended] [--report-lang en\|es]` | A report rendered from the ledger, to stdout (the menu action writes the files). |
| `odoo-dwg migrate findings links --source A --target B` | Every reference link in the ledger, requested; the ones that do not answer, named. Never a URL recorded as evidence. |

Anything that changes the host stays in the menus behind its confirmation phrase. A read-only command that
finds something to act on names the menu action; it does not perform it. Three skills in `.claude/skills/`
are thin wrappers over the first four commands.

| Seed a demo source database | Prepares the source version (plain Odoo clone, venv, config — none of which the chain itself builds) and writes `seed_demo.sh`, which builds a database with Odoo's demo data and dumps it in the format the driver takes ([migration](migration.md#rehearsing-before-there-is-a-client-dump)). | Previewed, confirmed |
| Module fates in this chain | Reads only. For each module named: renamed to X, absorbed into Y, or nothing declared — from each step's own `apriori.py`. | — |
| Follow a running migration | Reads only. Where the chain is (every step, including those not reached), what the running step is saying, and what it reached for outside its own machine since that step began. Stopping it leaves the driver alone ([migration](migration.md#following-a-run-while-it-happens)). | — |
| Generate the migration tester | Writes an add-on of the tool's own into each step's `custom`, with one probe per class of change *this chain* contains, taken from its own analysis files. Names the classes the chain never exercises ([migration](migration.md#rehearsing-against-a-module-built-to-break)). | Previewed, confirmed |
| Check the migration tester | Reads only. Asks a database what became of each probe's subject; reports what disappeared unannounced and what a script left behind, first. | — |
| Capture a database's mail in Mailpit | Same as the workspace action, for the migration's databases. | Phrase `CAPTURE` |
| Restore a database's mail configuration | The step before cutover: the migrated database mails out again through the client's own servers. | Phrase `RESTORE` |
| Check whether a database can mail out | Reads only. Use it after restoring, before cutover. | — |
| Take in a client copy | Restore the client's dump into a reference, create a read-only role, unpack and classify the add-ons archive, identify the core (official or OCB, and the commit), unpack the filestore, build the source from what the client runs, copy the reference to a working database, survey what the copy can act on, check each installed module along the chain across all OCA repositories, scan the client's own code for network calls, rehearse uninstalling modules on a throwaway clone of a neutralised copy, comparing every table, audit the client's own modules from their data (use since a date, survival in a migrated database, prints from an access log), find bank statement lines imported twice, proven by the bank's own balances, and list closed periods' unreconciled lines the accountant may leave behind (source up to 13.0), and find journal codes the target refuses. Each writes guarded SQL for the first step's pre hook and deletes nothing. Each step records its findings ([migration](migration.md#taking-in-a-client-copy)). | Each previewed and confirmed; phrase `COPY` to copy, `REHEARSE` to rehearse an uninstall |
| Neutralise a database | Captures the mail, then switches off every cron but housekeeping and takes tax/EDI, payment, delivery, OAuth, calendar, webhook and IAP integrations out of production, pointing `web.base.url` at the local instance — recording every change inside the database ([egress control](egress-control.md#neutralising-a-copy-of-production)). Also in a workspace's menu. | Phrase `NEUTRALISE` |
| Give a neutralised database its production settings back | The cutover step: the first run's recorded values back, the mail capture restored; names the rows production never had (left off) before asking. Never run by anything else. | Phrase `RESTORE PRODUCTION` |
| Check whether a database can act on the outside | Reads only. What can still act, rule by rule, and the mail verdict. | — |
| Findings and client reports | The environment's findings ledger: start it, add findings from a JSON file, record the client's decisions (earlier ones kept), set phases, withdraw a finding (to the corrections log), and write the client and extended reports in English or Spanish ([migration](migration.md#recording-what-the-migration-finds)). | Each change previewed, confirmed |

## The generated driver

`run_migration.sh <source-dump>` (inside an environment) preflights the host, restores the dump, verifies
the database before step 1, then runs each step with a `pg_dump` checkpoint after every success — a re-run
resumes from the last good checkpoint. Any preflight failure exits non-zero with a `[preflight-fail]` line;
the driver's own aborts use a `[fail]` line — a checkpoint that cannot be written, a step that failed (it
names the step's log file), a step whose OpenUpgrade code is not on disk, or checkpoints left by a different
source dump.
Details: [migration](migration.md).
