## MODIFIED Requirements

### Requirement: Checkpoint after each step and resume on failure

The driver SHALL `pg_dump` the working database after each successful step and, on a failed step, stop and
leave the last good checkpoint intact so a re-run resumes from it rather than restarting from the source.

On a re-run the driver SHALL restore the newest checkpoint into the working database before the first
pending step. A failed step can leave the database half-migrated, because OpenUpgrade commits module by
module, and that state must never be migrated again.

The driver SHALL record the SHA-256 of the source dump with the first checkpoint, and SHALL refuse to resume
with a different dump.

#### Scenario: Re-run resumes from the last good checkpoint

- **WHEN** step 5 of a chain fails after steps 1–4 succeeded
- **THEN** checkpoints for steps 1–4 remain and re-running the driver resumes at step 5, not at the source

#### Scenario: The half-migrated database is replaced before resuming

- **WHEN** step 16.0 failed after checkpoints for the source and 15.0 were written
- **THEN** the re-run restores the 15.0 checkpoint into the working database and only then runs step 16.0

#### Scenario: A different source dump is refused

- **WHEN** the driver is re-run with a dump whose SHA-256 differs from the one its checkpoints came from
- **THEN** it stops before touching the database and says the checkpoints belong to another dump

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
- **THEN** its command runs the OpenUpgrade 13.0 checkout's `odoo-bin` from that step's virtualenv with an
  `config `addons_path`` that includes the checkout's own `addons` directory, and includes neither
  `--upgrade-path` nor `--load`

#### Scenario: An add-on's own migration script runs

- **WHEN** the Odoo 13 step migrates a database with the `iap` module installed
- **THEN** that add-on's `migrations/13.0.1.0` scripts run, so `company_id` is renamed to its legacy name and
  its data moved into `company_ids`, rather than the column surviving unmigrated
