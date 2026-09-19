# migration-run Specification

## Purpose

Runs the chain one version at a time against a copy of the source database, checkpointing after each step so a failure is resumable, and never touching production data.

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

The system SHALL run each step with the target version's `odoo-bin` from that step's virtualenv, using
`--update all --stop-after-init`, and SHALL shape the command to that branch's OpenUpgrade layout.

For Odoo ≥ 14 the command SHALL load `base,web,openupgrade_framework` and point `--upgrade-path` at
`openupgrade_scripts/scripts`.

For Odoo ≤ 13 the migration scripts live inside each add-on (`addons/<module>/migrations/<version>/`) rather
than under an upgrade path, and there is no `openupgrade_framework` module to load. That step SHALL therefore
run the OpenUpgrade fork's own `odoo-bin` with **an explicit add-ons path naming the fork's `addons`
directory** (alongside the environment's per-version custom and OCA directories), and without
`--upgrade-path` or `--load`. The add-ons path MUST NOT be left to a default or to an environment's own
configuration: a path that resolves to some other copy of Odoo's add-ons silently skips every non-core
migration script while the step still reports success.

#### Scenario: A modern step loads openupgrade_framework

- **WHEN** the step upgrading to Odoo 18 is emitted
- **THEN** its command includes `--update all --stop-after-init` and `--load=base,web,openupgrade_framework` with `--upgrade-path` set to the OpenUpgrade 18.0 scripts

#### Scenario: The 13.0 step runs the fork's add-ons explicitly

- **WHEN** the step upgrading to Odoo 13 is emitted
- **THEN** its command runs the OpenUpgrade 13.0 checkout's `odoo-bin` from that step's virtualenv with a
  config whose `addons_path` names the checkout's own `addons` directory, and includes neither
  `--upgrade-path` nor `--load`

#### Scenario: An add-on's own migration script runs

- **WHEN** the Odoo 13 step migrates a database with the `iap` module installed
- **THEN** that add-on's `migrations/13.0.1.0` scripts run, so `company_id` is renamed to its legacy name and
  its data moved into `company_ids`, rather than the column surviving unmigrated

### Requirement: Checkpoint after each step and resume on failure

The driver SHALL `pg_dump` the working database after each successful step and, on a failed step, stop and
leave the last good checkpoint intact so a re-run resumes from it rather than restarting from the source.

On a re-run the driver SHALL restore the newest checkpoint into the working database before the first
pending step. A failed step can leave the database half-migrated, because OpenUpgrade commits module by
module, and that state must never be migrated again.

The driver SHALL record the SHA-256 of the source dump with the first checkpoint, and SHALL refuse to resume
with a different dump. A checkpoint that cannot be written SHALL abort the run naming the step: a chain that
kept going would have no recovery point at all while reporting that it had one. A checkpoint SHALL become visible only once it is complete, so an interrupted
`pg_dump` never leaves a truncated file that a later run would restore.

A run that starts from the source rather than resuming SHALL discard the checkpoints already present, so a
previous chain's dumps are never mistaken for this one's. A resume SHALL restore the newest checkpoint that
is contiguous with the chain: if the checkpoint for a step is missing while a later one exists, the driver
SHALL resume from the last unbroken point rather than skipping the gap.

#### Scenario: Re-run resumes from the last good checkpoint

- **WHEN** step 5 of a chain fails after steps 1–4 succeeded
- **THEN** checkpoints for steps 1–4 remain and re-running the driver resumes at step 5, not at the source

#### Scenario: The half-migrated database is replaced before resuming

- **WHEN** step 16.0 failed after checkpoints for the source and 15.0 were written
- **THEN** the re-run restores the 15.0 checkpoint into the working database and only then runs step 16.0

#### Scenario: A checkpoint that cannot be written stops the chain

- **WHEN** `pg_dump` fails while checkpointing a step
- **THEN** the driver exits non-zero naming that checkpoint, runs no further step, and leaves no
  half-written file behind

#### Scenario: A fresh run discards earlier checkpoints

- **WHEN** the driver is started from the source with checkpoints from a previous chain still on disk
- **THEN** those checkpoints are removed before the source is restored, so no later step can resume onto them

#### Scenario: A gap in the checkpoints is not skipped

- **WHEN** the checkpoints for the source and 16.0 exist but the one for 15.0 does not
- **THEN** the driver resumes from the source and re-runs 15.0, rather than restoring 16.0 and continuing

#### Scenario: An interrupted checkpoint is not resumed from

- **WHEN** a `pg_dump` is interrupted while writing a step's checkpoint
- **THEN** no checkpoint file for that step exists afterwards, and the re-run resumes from the previous one

#### Scenario: A different source dump is refused

- **WHEN** the driver is re-run with a dump whose SHA-256 differs from the one its checkpoints came from
- **THEN** it stops before touching the database and says the checkpoints belong to another dump

### Requirement: Driver preflight before touching the database

`run_migration.sh` SHALL run the host-scope preflight (chain tools, PostgreSQL, dump integrity) before
restoring anything, and the database-scope preflight (source-version match from `ir_module_module`,
installed modules, per-step addons coverage) immediately after the initial restore and before step 1. Any
failed check SHALL abort the driver with a non-zero exit and a message naming the failed check; coverage
findings SHALL name the directory the operator must fill.

#### Scenario: Host failure aborts before restore

- **WHEN** the driver starts on a host where `uv` is missing
- **THEN** it exits non-zero naming the failed check, without creating or restoring the working database

#### Scenario: Version mismatch aborts after restore, before step 1

- **WHEN** the restored database's `base` version does not match the environment's declared source
- **THEN** the driver exits non-zero naming the mismatch and runs no migration step
