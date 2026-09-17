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

#### Scenario: A 13 → 15 chain stages each bump from the previous stage

- **WHEN** staging module `client_sales` for a 13 → 15 chain
- **THEN** the plan migrates the source copy 13→14 into `addons/odoo14/custom/client_sales`, then that output 14→15 into `addons/odoo15/custom/client_sales`, leaving the operator's source untouched

### Requirement: The staging tool is a prepared host prerequisite

`odoo-module-migrator` SHALL be installed into a dedicated uv-managed tool venv under the migration base
directory via an opt-in previewed plan, SHALL be detected by the migration preflight when staging is
requested, and MUST NOT become a runtime dependency of odoo_dwg itself.

#### Scenario: Staging without the tool is caught by preflight

- **WHEN** the staging action runs on a host where the tool venv does not exist
- **THEN** the preflight reports it MISSING with the plan that installs it, and no staging command runs

### Requirement: Breaking-reference detection from OpenUpgrade analysis files

For each staged module and step, the system SHALL parse the step's OpenUpgrade analysis files
(`openupgrade_scripts/scripts/<module>/<ver>/upgrade_analysis.txt` in the already-cloned OpenUpgrade
checkout) into removed/renamed core field and model records, scan the staged module's source (Python and
XML) for occurrences of those names, and report each match as a **candidate** finding with file and line.
The report MUST state that matches are leads requiring developer confirmation, not proof.

#### Scenario: A renamed core field used in a view is flagged

- **WHEN** step 17.0's analysis lists a `res.partner` field rename and the staged module's XML references the old name
- **THEN** the report lists the module, step, file, line, old and new name as a candidate finding

### Requirement: Generated migration scaffolds are additive

For each module/step with candidate findings, the system SHALL write a
`migrations/<target-version>/pre-migration.py` stub containing a generated-file header, the
openupgradelib import, and one commented TODO entry per finding. If the target file already exists the
stub SHALL be written as a sibling `pre-migration.generated.py` instead — operator code is never
overwritten.

#### Scenario: Existing migration file is preserved

- **WHEN** the staged module already ships `migrations/17.0.1.0/pre-migration.py`
- **THEN** the scaffold is written alongside as `pre-migration.generated.py` and the existing file is untouched

### Requirement: Staging report for developer review

The system SHALL produce, per module, a persisted staging report in the environment covering every step:
the tool's INFO/WARNING/ERROR log carried verbatim, candidate findings, and scaffolds written. The report
MUST state that staging is a prepared starting point and that the developer's review completes the
migration — the system SHALL NOT mark a module as migrated.

#### Scenario: Tool errors surface in the report

- **WHEN** `odoo-module-migrator` logs an ERROR (e.g. a dependency removed upstream) during a step
- **THEN** the report shows that ERROR verbatim under that module and step

