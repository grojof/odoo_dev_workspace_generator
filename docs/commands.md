---
type: reference
title: "Command reference"
description: "Every CLI invocation, menu action, confirmation phrase, and environment variable."
audience: [developer, operator]
updated: 2026-07-18
---

# Command reference

The tool is one executable with an interactive menu and three direct subcommands. Every host-mutating
action assembles a command **plan**, previews it, and runs it only after confirmation; destructive actions
additionally require typing an exact phrase.

## Invocation

| Command | What it opens |
|---|---|
| `python3 -m odoo_dwg` | Interactive top-level menu (language prompt on first screen) |
| `python3 -m odoo_dwg workspace` | Workspace section directly |
| `python3 -m odoo_dwg provision` | Provisioning section directly |
| `python3 -m odoo_dwg migrate` | Migration mode directly |
| `odoo-dwg …` | Console-script equivalent (after `pip install -e .`) |

Flags: `--lang {en,es}` (UI language) · `--version` · `-h/--help`.

## Environment variables

| Variable | Effect |
|---|---|
| `ODWG_LANG=en\|es` | UI language without the startup prompt (artifacts are always English) |

## Menus and actions

Every menu shows a numbered list; `0` (or `Back`/`Cancel`) always returns without acting.

### Workspaces (create / manage)

| Action | Behavior | Guard |
|---|---|---|
| Create a workspace → New (quick) | Interactive minimal profile, then full generation plan | Create-only: refuses to clobber an existing workspace |
| Create a workspace → From a profile file | Same, loading a JSON profile (see [configuration-reference](configuration-reference.md)) | idem |
| Manage → Regenerate a venv | Removes and rebuilds one instance venv | Phrase `REBUILD` |
| Manage → Refresh shared repos | `git pull --ff-only` on present clones in the shared cache | Preview + confirm |
| Manage → Add a version | Extends an existing workspace with a new Odoo version | Preview + confirm |

### System provisioning (optional; the Ubuntu releases in the [support matrix](support-matrix.md))

| Action | Behavior | Guard |
|---|---|---|
| Check host readiness | Read-only capability table (host release, build deps, PostgreSQL + role + server version, wkhtmltopdf, Node, host `python3`, uv interpreters) | Never mutates |
| Apply (install what's missing) | Plans installs for missing capabilities; Node + rtlcss is a separate opt-in | Root required; preview + confirm |

### Migration (OpenUpgrade 12→19)

| Action | Behavior | Guard |
|---|---|---|
| Generate a migration environment | Chain-scoped host preflight table first, then the full plan (clones, uv venvs with `--overrides` repairs, per-step confs, addons layout, checkpointing driver) | MISSING checks require explicit confirmation; preview + confirm |
| Preflight check | Read-only verification: chain tools, PostgreSQL, dump integrity, and — against a named database — version match, installed modules, per-step addons coverage | Never mutates |
| Stage custom modules | Per chain step, copies the previous stage and runs `odoo-module-migrator` on it; then analysis findings, inert `pre-migration.py` scaffolds, and a per-module report | Source dir never modified; phrase `RESTAGE` to replace staged code |
| Clean a migration environment | Removes one `<src>-to-<tgt>` directory; the shared `.repos` cache is a separate opt-in | Phrase `DELETE`; the PostgreSQL DB is never touched |

## The generated driver

`run_migration.sh <source-dump>` (inside an environment) preflights the host, restores the dump, verifies
the database before step 1, then runs each step with a `pg_dump` checkpoint after every success — a re-run
resumes from the last good checkpoint. Any preflight failure exits non-zero with a `[preflight-fail]` line.
Details: [migration](migration.md).
