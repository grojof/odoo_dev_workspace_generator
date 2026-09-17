# migration-preflight Specification

## Purpose

Verifies, before a migration runs and again from inside the driver, that the host, the PostgreSQL server, the source dump and the database itself can actually carry the chain — naming exactly what is missing, including which addons directory to fill, rather than failing mid-upgrade.

## Requirements
### Requirement: Chain-scoped host readiness check

The system SHALL provide a read-only migration preflight that verifies the host tools required by the
*specific* chain: `uv` always; `docker` (binary present), the Docker daemon responding, and the presence of
the fallback images only when the chain includes an Odoo 12/13 step. It SHALL also verify PostgreSQL
reachability and the development role. The result SHALL be rendered as a capability table
(check, state, detail) with states OK / WARN / MISSING / INFO, and the check MUST NOT modify the host.

#### Scenario: Docker checks only appear for chains that need them

- **WHEN** the preflight runs for a 14 → 18 chain (fully native)
- **THEN** the report contains no Docker rows, and `uv` and PostgreSQL are still verified

#### Scenario: Docker daemon distinct from binary

- **WHEN** `docker` is installed but the daemon is not running (or the user lacks permission)
- **THEN** the report marks the binary OK and the daemon MISSING/WARN with the underlying error detail

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
the module somewhere in that step's `addons_path` (target core, OpenUpgrade, the environment's per-version
OCA dir, or the per-version custom dir). Modules found nowhere SHALL be reported per step with the exact
directory where the operator should place them.

#### Scenario: A custom module missing for one step is pinpointed

- **WHEN** module `client_sales` is installed in the database but absent from every source of step 16.0
- **THEN** the report names `client_sales`, the step, and the `addons/odoo16/custom` directory to fill

### Requirement: Custom modules are flagged for per-version adaptation

Modules classified as custom (found in the per-version custom dir, or found nowhere) SHALL additionally be
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

#### Scenario: Menu action runs without a database

- **WHEN** the operator runs the preflight from the menu without naming a database
- **THEN** the host-scope checks run and the database-scope checks are reported as skipped, not failed

