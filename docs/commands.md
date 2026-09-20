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
| Manage → Redirect a database's mail to Mailpit | Points every mail server of a named database at `127.0.0.1:1025` and clears its credentials, and deactivates fetchmail servers. Odoo 12–19. Rehearsal copies only ([egress-control](egress-control.md#a-copied-database-still-mails-out-redirect-it)). | Phrase `REDIRECT` |

### System provisioning (optional; the Ubuntu releases in the [support matrix](support-matrix.md))

| Action | Behavior | Guard |
|---|---|---|
| Check host readiness | Read-only capability table (host release, build deps, PostgreSQL + role + server version + loopback auth, wkhtmltopdf, Node and rtlcss, host `python3`, uv interpreters, OpenSnitch and whether it is hardened, Mailpit) | Never mutates |
| Apply (install what's missing) | Plans installs for missing capabilities. rtlcss (right-to-left languages only), the outbound firewall (OpenSnitch) and the mail capture (Mailpit) are separate opt-ins ([egress-control](egress-control.md)). | Root required; preview + confirm |
| Outbound firewall and mail capture (on/off, uninstall) | Shows both components' state. Turns each off or on (persistent across restarts), or uninstalls it. For OpenSnitch it lists what `apt` removes first and keeps your own rules. ([details](egress-control.md#turning-it-off-or-uninstalling)) | Root required; preview + confirm; phrase `UNINSTALL` to uninstall |

### Migration (OpenUpgrade 12→19)

| Action | Behavior | Guard |
|---|---|---|
| Generate a migration environment | Chain-scoped host preflight table first, then the full plan (clones, uv venvs with `--overrides` repairs, per-step confs, addons layout, checkpointing driver) | MISSING checks require explicit confirmation; preview + confirm |
| Preflight check | Read-only verification: chain tools, PostgreSQL, dump integrity, and — against a named database — version match, installed modules, per-step addons coverage | Never mutates |
| Stage custom modules | Per chain step, copies the previous stage and runs `odoo-module-migrator` on it; then analysis findings, inert `pre-migration.py` scaffolds, and a per-module report | Source dir never modified; phrase `RESTAGE` to replace staged code |
| Clean a migration environment | Removes one `<src>-to-<tgt>` directory; the shared `.repos` cache is a separate opt-in | Phrase `DELETE`; the PostgreSQL DB is never touched |
| Redirect a database's mail to Mailpit | Same as the workspace action, for the migration's databases. Never for a database going back to production. | Phrase `REDIRECT` |

## The generated driver

`run_migration.sh <source-dump>` (inside an environment) preflights the host, restores the dump, verifies
the database before step 1, then runs each step with a `pg_dump` checkpoint after every success — a re-run
resumes from the last good checkpoint. Any preflight failure exits non-zero with a `[preflight-fail]` line;
the driver's own aborts use a `[fail]` line — a checkpoint that cannot be written, a step that failed (it
names the step's log file), a step whose OpenUpgrade code is not on disk, or checkpoints left by a different
source dump.
Details: [migration](migration.md).
