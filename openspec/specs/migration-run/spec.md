# migration-run Specification

## Purpose
TBD - created by archiving change add-openupgrade-migration. Update Purpose after archive.
## Requirements
### Requirement: Sequential chain with no skipped versions

The system SHALL compute the migration chain as every version from the one after the source up to the target,
in ascending order, and run each step in that order — never skipping a version (per official OpenUpgrade).

#### Scenario: A 13 → 18 migration runs each intermediate step

- **WHEN** the chain is computed for source 13.0 and target 18.0
- **THEN** the ordered steps upgrade to 14.0, 15.0, 16.0, 17.0, then 18.0, with no gaps

### Requirement: Start from a copy of the source, never production

The `run_migration.sh` driver SHALL begin by restoring a supplied source database dump into a working database
on the shared migration cluster and checkpointing that initial state, and MUST NOT operate on the original
production database.

#### Scenario: Source is restored into a working DB and checkpointed

- **WHEN** the driver starts with a source dump
- **THEN** it creates a working database, restores the dump into it, and writes an initial checkpoint before any step runs

### Requirement: Per-branch odoo-bin command shape

The system SHALL run each step with the target version's `odoo-bin` using `--update all --stop-after-init` and
the OpenUpgrade upgrade path. For Odoo ≥ 14 the command SHALL load `base,web,openupgrade_framework` and point
`--upgrade-path` at `openupgrade_scripts/scripts`; for the 12/13 branches it SHALL use their older layout
rather than assuming the ≥ 14 form.

#### Scenario: A modern step loads openupgrade_framework

- **WHEN** the step upgrading to Odoo 18 is emitted
- **THEN** its command includes `--update all --stop-after-init` and `--load=base,web,openupgrade_framework` with `--upgrade-path` set to the OpenUpgrade 18.0 scripts

### Requirement: Checkpoint after each step and resume on failure

The driver SHALL `pg_dump` the working database after each successful step and, on a failed step, stop and
leave the last good checkpoint intact so a re-run resumes from it rather than restarting from the source.

#### Scenario: Re-run resumes from the last good checkpoint

- **WHEN** step 5 of a chain fails after steps 1–4 succeeded
- **THEN** checkpoints for steps 1–4 remain and re-running the driver resumes at step 5, not at the source

### Requirement: Docker fallback for the Python-3.6 step

For the step that runs Odoo 13 (Python 3.6) — i.e. a 12 → 13 migration — the system SHALL emit a Docker-based
recipe (using the official `odoo:13.0` image) that runs the equivalent OpenUpgrade command against the shared
PostgreSQL, so the native chain can resume from the resulting checkpoint. The generator emits the recipe only;
it never runs Docker itself.

#### Scenario: The Odoo-13 step is emitted as a Docker recipe

- **WHEN** a chain includes the 12 → 13 step
- **THEN** that step is emitted as a `docker run` recipe against the shared database, and the remaining native steps consume its checkpoint

### Requirement: Driver preflight before touching the database

`run_migration.sh` SHALL run the host-scope preflight (chain tools, PostgreSQL, dump integrity) before
restoring anything, and the database-scope preflight (source-version match from `ir_module_module`,
installed modules, per-step addons coverage) immediately after the initial restore and before step 1. Any
failed check SHALL abort the driver with a non-zero exit and a message naming the failed check; coverage
findings SHALL name the directory the operator must fill.

#### Scenario: Host failure aborts before restore

- **WHEN** the driver starts on a chain that needs Docker and the daemon is not responding
- **THEN** it exits non-zero naming the Docker check, without creating or restoring the working database

#### Scenario: Version mismatch aborts after restore, before step 1

- **WHEN** the restored database's `base` version does not match the environment's declared source
- **THEN** the driver exits non-zero naming the mismatch and runs no migration step

