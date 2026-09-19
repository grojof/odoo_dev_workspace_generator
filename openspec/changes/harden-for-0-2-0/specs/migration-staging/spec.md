## REMOVED Requirements

### Requirement: The staging tool is a prepared host prerequisite

**Reason**: Its scenario said a missing tool is "caught by preflight". The preflight has no such check
(`odoo_dwg/preflight.py`): the staging action itself warns and offers the install plan. Replaced by
"The staging tool is installed on demand".

### Requirement: Breaking-reference detection from OpenUpgrade analysis files

**Reason**: Its scenario said a *renamed* core field is flagged. The analysis parser produces removed models
and fields only (`odoo_dwg/analysis.py`), and the ≤ 13 fork keeps its analysis files inside each add-on.
Replaced by "Removed-reference detection from OpenUpgrade analysis files".

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Generated migration scaffolds are additive

For each module/step with candidate findings, the system SHALL write a
`migrations/<target-version>.1.0.0/pre-migration.py` stub containing a generated-file header, the
openupgradelib import, and one commented TODO entry per finding. If the target file already exists the
stub SHALL be written as a sibling `pre-migration.generated.py` instead — operator code is never
overwritten.

#### Scenario: Existing migration file is preserved

- **WHEN** the staged module already ships `migrations/17.0.1.0.0/pre-migration.py`
- **THEN** the scaffold is written alongside as `pre-migration.generated.py` and the existing file is untouched
