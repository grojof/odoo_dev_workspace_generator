# migration-staging Specification

## Purpose

Brings an operator's custom modules along the chain one step at a time, running the OCA module migrator per bump and cross-referencing the result against OpenUpgrade's analysis files, so breaking references surface as reviewable findings and inert scaffolds instead of runtime errors.

## Requirements

### Requirement: Stepwise staging of custom modules

The system SHALL provide a staging action that, for each selected custom module and each step of the
chain, copies the previous step's staged code (the operator's source directory for the first step) into
the environment's `addons/odoo<major>/custom` and runs `odoo-module-migrator` for exactly that version
bump on the copy. The operator's original source directory MUST NOT be modified. All copies and tool
invocations SHALL go through the plan → preview → apply flow.

Every operator-supplied value SHALL be validated before it reaches a plan: the source directory MUST exist,
each named module MUST be a valid Odoo module name (`^[a-z_][a-z0-9_]{0,63}$`) and MUST be present in that
directory. A value failing any of these SHALL stop the action naming the value, with nothing planned.

#### Scenario: A module name carrying shell syntax is refused

- **WHEN** the operator names `sale; rm -rf ~` among the modules to stage
- **THEN** the action stops naming that value, and no command is planned

#### Scenario: A module absent from the source directory is refused

- **WHEN** the operator names a module the source directory does not contain
- **THEN** the action stops naming it, rather than planning a copy of a directory that is not there

#### Scenario: A 13 → 15 chain stages each bump from the previous stage

- **WHEN** staging module `client_sales` for a 13 → 15 chain
- **THEN** the plan migrates the source copy 13→14 into `addons/odoo14/custom/client_sales`, then that output 14→15 into `addons/odoo15/custom/client_sales`, leaving the operator's source untouched

### Requirement: Generated migration scaffolds are additive

For each module/step with candidate findings, the system SHALL write a
`migrations/<target-version>.1.0.0/pre-migration.py` stub containing a generated-file header, the
openupgradelib import, and one commented TODO entry per finding. If the target file already exists the
stub SHALL be written as a sibling `pre-migration.generated.py` instead — operator code is never
overwritten.

#### Scenario: Existing migration file is preserved

- **WHEN** the staged module already ships `migrations/17.0.1.0.0/pre-migration.py`
- **THEN** the scaffold is written alongside as `pre-migration.generated.py` and the existing file is untouched

### Requirement: Staging report for developer review

The system SHALL produce, per module, a persisted staging report in the environment covering every step:
the tool's INFO/WARNING/ERROR log carried verbatim, candidate findings, and scaffolds written. The report
MUST state that staging is a prepared starting point and that the developer's review completes the
migration — the system SHALL NOT mark a module as migrated.

#### Scenario: Tool errors surface in the report

- **WHEN** `odoo-module-migrator` logs an ERROR (e.g. a dependency removed upstream) during a step
- **THEN** the report shows that ERROR verbatim under that module and step

### Requirement: The staging tool is installed on demand

`odoo-module-migrator` SHALL live in its own virtualenv inside the migration environment, installed through
an opt-in previewed plan when the staging action needs it, and MUST NOT become a runtime dependency of
odoo_dwg itself.

#### Scenario: Staging without the tool offers to install it

- **WHEN** the staging action runs on a host where the tool venv does not exist
- **THEN** the flow warns, previews the plan that installs it, and stages nothing unless that plan is applied

### Requirement: Removed-reference detection from OpenUpgrade analysis files

For each staged module and step, the system SHALL parse that step's OpenUpgrade analysis files — under
`openupgrade_scripts/scripts/<module>/<ver>/` from 14.0, and inside each add-on's `migrations/<ver>/` in a
≤ 13 fork — into the core models and fields the step removes, scan the staged module's Python and XML for
those names, and report each match as a **candidate** finding with file and line. The report MUST state that
matches are leads requiring developer confirmation, not proof.

#### Scenario: A removed core field used in a view is flagged

- **WHEN** step 17.0's analysis lists a removed `res.partner` field and the staged module's XML references it
- **THEN** the report lists the module, step, file, line and the field as a candidate finding

#### Scenario: A module with no matches is reported clean

- **WHEN** a staged module references nothing the step removes
- **THEN** its report lists no candidate findings for that step, and no scaffold is written
