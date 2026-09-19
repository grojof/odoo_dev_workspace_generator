# migration-preflight Specification

## Purpose

Verifies, before a migration runs and again from inside the driver, that the host, the PostgreSQL server, the source dump and the database itself can actually carry the chain — naming exactly what is missing, including which addons directory to fill, rather than failing mid-upgrade.

## Requirements

### Requirement: Source dump integrity check

The preflight SHALL verify the supplied source dump: the file exists and is readable, and
`pg_restore --list` parses it — which also enforces the custom/tar dump format the driver requires. A
plain-SQL dump SHALL be reported as a failure with a message stating the required format.

#### Scenario: Plain SQL dump is rejected with guidance

- **WHEN** the preflight is pointed at a plain-SQL dump file
- **THEN** the dump check fails, stating that a custom-format dump (`pg_dump -Fc`) is required

### Requirement: Database-scope verification

Given a restored working database, the preflight SHALL read the actual source Odoo version from
`ir_module_module` (the `base` module's `latest_version`) and compare it against the declared source
version, and SHALL list the installed modules. A version mismatch SHALL be reported as a failure before
any migration step runs.

#### Scenario: Declared source does not match the database

- **WHEN** the environment was generated for source 13.0 but the restored database's `base` version is 12.0
- **THEN** the preflight reports the mismatch and the driver aborts before step 1

### Requirement: Per-step addons coverage

For every module installed in the database, the preflight SHALL verify that each step of the chain can find
the module somewhere that step resolves modules from:
- its `addons_path`: the per-version custom and OCA dirs, OpenUpgrade, and the target core;
- the core add-ons `odoo-bin` adds itself.

For a step up to 13.0 those are the OpenUpgrade fork's own `addons` and `odoo/addons`; no separate Odoo
clone exists.

Before reporting a module as missing, the check SHALL consult that step's OpenUpgrade checkout for the
renames and merges it declares (`openupgrade_scripts/apriori.py` from 14.0,
`odoo/addons/openupgrade_records/lib/apriori.py` in a ≤ 13 fork), and SHALL treat a module whose declared successor resolves in that step's
sources as covered.

A module that resolves nowhere and that OpenUpgrade does not account for SHALL be classified by its recorded
author:

- authored by Odoo — a core module dropped upstream. Reported as a **warning** naming the module and the
  step, and it SHALL NOT block the migration, because the upgrade itself removes it and the operator has
  nothing to supply.
- authored by anyone else — code the step genuinely needs. Reported as **blocking**, naming the module, the
  step, and the exact directory where the operator should place it.

The interactive preflight and the checks embedded in the migration driver SHALL apply the same
classification, so that the two cannot disagree about whether a chain can run.

#### Scenario: A step whose sources are not on disk is named as such

- **WHEN** coverage runs for a step whose OpenUpgrade and Odoo directories do not exist
- **THEN** it reports that the step's sources are not on disk and classifies no module, rather than
  reporting every installed module — `base` included — as dropped or missing

#### Scenario: A custom module missing for one step is pinpointed

- **WHEN** module `client_sales` is installed in the database but absent from every source of step 16.0
- **THEN** the report names `client_sales`, the step, and the `addons/odoo16/custom` directory to fill, and
  the module is in the blocking class

#### Scenario: A module OpenUpgrade renames is covered by its successor

- **WHEN** module `web_editor` is installed and step 19.0's OpenUpgrade checkout declares it renamed to
  `html_editor`, which that step's core provides
- **THEN** the module is reported as covered, not as missing, and nothing asks the operator to place it

#### Scenario: A module OpenUpgrade merges into another is covered

- **WHEN** module `web_kanban_gauge` is installed and step 17.0's OpenUpgrade checkout declares it merged
  into `web`
- **THEN** the module is reported as covered, not as missing

#### Scenario: A core module dropped upstream warns instead of blocking

- **WHEN** an Odoo-authored module is installed, resolves in no source of step 14.0, and that step's
  OpenUpgrade checkout declares neither a rename nor a merge for it
- **THEN** it is reported as a warning naming the module and the step, and the chain is still allowed to run

#### Scenario: The driver refuses only on the blocking class

- **WHEN** the driver's embedded checks find warnings but no blocking modules
- **THEN** it prints the warnings with their reason and proceeds to the first step

#### Scenario: The driver aborts when the operator's code is missing

- **WHEN** the driver's embedded checks find a module in the blocking class
- **THEN** it aborts non-zero before any migration step runs — the check reads the restored working
  database, so the restore has happened and no upgrade has — naming the module, the step and the directory
  to fill

#### Scenario: A legacy step finds core modules in the fork

- **WHEN** the chain includes the 13.0 step and the database has `base` and `web` installed
- **THEN** both resolve in the 13.0 fork (`odoo/addons` and `addons`) and neither is reported missing, in the
  interactive preflight and in the driver alike

### Requirement: Custom modules are flagged for per-version adaptation

Modules found in a step's per-version custom dir SHALL additionally be
flagged with a warning that presence is necessary but not sufficient: each target version requires the
module's code *adapted to that version's breaking changes* and, when data/schema is involved, its own
`migrations/` scripts. The report SHALL reference the staging workflow (see the `migration-staging`
capability) as the prepared path for this work.

#### Scenario: A present custom module still carries the adaptation warning

- **WHEN** module `client_sales` exists in `addons/odoo17/custom` and coverage passes for step 17.0
- **THEN** the report still lists `client_sales` as custom with a note that its 17.0 code must be adapted (e.g. view `attrs` removal) and reviewed

### Requirement: Preflight is reusable from menu and flows

The preflight SHALL be exposed as an independent migration-menu action (host scope always; database scope
when the operator names an existing database) and the same implementation SHALL be reused by the generate
flow and the run driver rather than duplicating checks ad hoc.

A database named by the operator MUST be a valid PostgreSQL database name before any query is built with
it; otherwise the action SHALL stop naming the value.

#### Scenario: Menu action runs without a database

- **WHEN** the operator runs the preflight from the menu without naming a database
- **THEN** the host-scope checks run and the database-scope checks are reported as skipped, not failed

#### Scenario: An invalid database name is refused

- **WHEN** the operator names `db"; DROP DATABASE x --` as the database to verify
- **THEN** the action stops naming the value, and no query runs

### Requirement: Host readiness for a native chain

The system SHALL provide a read-only migration preflight that verifies the host tools every chain needs:
`uv`, PostgreSQL reachability, and the development role. Because every step runs natively, no chain requires
a container runtime and the preflight SHALL NOT check for one. The result SHALL be rendered as a capability
table (check, state, detail) with states OK / WARN / MISSING / INFO, and the check MUST NOT modify the host.

#### Scenario: The same tools are checked for every chain

- **WHEN** the preflight runs for a 14 → 18 chain and for a 12 → 19 chain
- **THEN** both report `uv` and PostgreSQL, and neither reports a container runtime

#### Scenario: A missing interpreter provider is reported

- **WHEN** `uv` is absent from the host
- **THEN** the report marks it MISSING, because no step can be built without it

#### Scenario: The check changes nothing

- **WHEN** the preflight runs against a host missing every prerequisite
- **THEN** it reports them and makes no change to the host
