# Proposal

## Why

The first real client intake was done by hand, and it took one afternoon, a dozen ad-hoc scripts and six
traps:
- a module that looked "installed without code" because its manifest was the legacy `__openerp__.py`;
- a comparison of the client's core against a shallow clone, which has no history;
- `git log --raw` hiding merge commits, so every file looked locally patched;
- an `awk` field split that took the path for the status;
- a PostgreSQL 14+ incompatibility surfacing as a `pg_restore` error;
- a read-only role whose hidden columns made a check skip rules silently.

Each trap is easy to hit again, and none of them is specific to that client. Then, to start the client's
Odoo 12 at all, the tool had nothing to offer. It builds the source version from **official** Odoo at the
branch head. A client may run **OCA/OCB** at an older commit, with dozens of OCA repositories and their
own modules, in a specific `addons_path` order.

This change turns that intake into commands. Their results are recorded in the findings ledger, and the
source version is built from what the client actually runs, so the source Odoo can be started on a
neutralised copy.

This is the first half of what was planned as "spec 3". The second half is:
- an outbound inventory written as findings;
- per-step availability across *all* OCA repositories;
- a scan of custom code for network calls.

It follows as its own change. This half is what stands between a client dump and a running source
instance.

## What Changes

- **An intake record per migration environment**, `<env root>/intake.json`. It holds:
  - the reference database and the read-only role;
  - the client's add-on directories, in their `addons_path` order;
  - **the core the client runs**: official Odoo or OCB, and the commit.

  The environment reads it. Without it, everything behaves exactly as today.
- **Restore a client dump** into a reference database the tool never modifies:
  - `--no-owner --no-acl`;
  - verified against the dump's table of contents;
  - every `pg_restore` error classified against a declared list of known, data-safe classes (first entry:
    `array_cat(anyarray)` aggregates on PostgreSQL 14+).

  An unknown error is a finding, never ignored.
- **Create a read-only role** on that reference:
  - `SELECT` only, read-only by default, no `TEMP`;
  - no access to a declared catalogue of secret columns: passwords, keys, tokens,
    `ir_config_parameter.value`, attachment contents;
  - a random password, stored only in `~/.pgpass`.
- **Unpack and classify the client's add-ons archive**, read-only, under `<env root>/client-src/`:
  - per repository: remote, branch, commit, commits ahead of upstream, uncommitted files;
  - per module: `__manifest__.py` **or** `__openerp__.py`, the directory that wins in the client's
    `addons_path` order, and duplicates;
  - per installed module: where it loads from, or that its code is missing.
- **Identify the client's core.** For each core file that differs from official Odoo's branch head, the
  tool looks for its content in the full history of official Odoo and OCA/OCB, merge commits included:
  - it names the flavour: official, OCB, or locally patched, with the patched files listed;
  - it finds the exact commit, the one whose tree matches the client's.
- **Build the source from what the client runs.** The source Odoo is cloned at the identified repository
  and commit, and its add-ons path is the client's directories in the client's order, then the core's.
- **Start the source version guarded.** `open_for_testing.sh` accepts the source version too: it
  re-neutralises, checks, and starts with no cron thread on loopback. The filestore can be unpacked into
  the environment's data directory for it.
- **Findings.** Each step writes its findings and data tables into the environment's findings ledger, in
  English, with the client-facing text left for the operator to write.

Out of scope, in the follow-up change:
- the outbound inventory as findings;
- availability across all OCA repositories;
- the custom-code network scan.

Also out of scope: writing client-facing text automatically.

Verifiable off-host:
- parsing, classification and plans, by unit tests;
- restore classification and the reader role, by a throwaway PostgreSQL;
- core identification, by a throwaway git history with a merge commit.

On the host: the client's archive and dump, and starting Odoo 12 on the neutralised copy.

## Capabilities

### New Capabilities
- `client-intake`: taking in a copy of a client's production:
  - the intake record;
  - restoring and classifying the dump;
  - the read-only role;
  - unpacking and classifying the add-ons archive;
  - identifying the core;
  - recording all of it as findings.

### Modified Capabilities
- `migration-environment`: the source version is built from the core and add-ons the intake identified,
  when there is an intake record.
- `migration-run`: the guarded start covers the source version as well as the chain's steps.

## Impact

- **New code:**
  - `odoo_dwg/intake.py`: pure parsing, classification and matching;
  - planners for restore, role, unpack and filestore;
  - `workflows/intake.py`, with a Migration menu entry;
  - `system.py` helpers for git history and tree reads;
  - changes to `MigrationEnv` and `plan_seed_environment`;
  - `render_open_for_testing_sh`.
- **Tests:**
  - unit tests for each classifier and plan;
  - `tools/verify_intake.py`: a throwaway PostgreSQL for restore classification and the reader role, and a
    throwaway git repository with a merge commit for core identification;
  - `tools/verify_migration_driver.py` and `tools/verify_generated_shell.py` extended to the source start.
- **Docs:**
  - `docs/migration.md`, with a new "Taking in a client copy" section;
  - `docs/commands.md`, `README.md`, `CHANGELOG.md`, `docs/roadmap.md`.
- **No runtime dependency.** `git`, `pg_restore` and `tar` are host tools already required.
- **No client data in the repository.** Fixtures use invented names.
