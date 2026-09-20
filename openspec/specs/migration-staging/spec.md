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

Re-staging a module whose staged code already exists SHALL require an exact-phrase confirmation: that code
is replaced outright and may carry the operator's own edits.

Where the migration tool requires a repository, the system SHALL make each stage directory a throwaway one
and commit the pre-migration state into it with an identity, hook path and signing settings of its own, so
that the operator's global git configuration — a mandatory signature, a global hook — can neither fail the
step nor run against their code. The generated report SHALL say that the stage directories are throwaway
repositories.

Every operator-supplied value SHALL be validated before it reaches a plan: the source directory MUST exist,
each named module MUST be a valid Odoo module name (`^[a-z_][a-z0-9_]{0,63}$`) and MUST be present in that
directory. A value failing any of these SHALL stop the action naming the value, with nothing planned.

#### Scenario: A module name carrying shell syntax is refused

- **WHEN** the operator names `sale; rm -rf ~` among the modules to stage
- **THEN** the action stops naming that value, and no command is planned

#### Scenario: Replacing staged code is confirmed first

- **WHEN** the operator stages a module that is already staged for some step of the chain
- **THEN** the action names that module and stages nothing unless the exact phrase is typed

#### Scenario: A signing-everything git configuration does not break staging

- **WHEN** the operator's global git config sets `commit.gpgsign = true` with no usable key
- **THEN** the stage commit still succeeds, because the step supplies its own signing and hook settings

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

`odoo-module-migrator` SHALL live in its own virtualenv under the shared `.tools` directory beside the
migration environments, pinned to a version this project has validated, installed through an opt-in
previewed plan when the staging action needs it, and MUST NOT become a runtime dependency of odoo_dwg
itself. It is shared because it is a host tool rather than part of any one environment: cleaning an
environment SHALL leave it in place, and the next environment SHALL reuse it.

#### Scenario: Staging without the tool offers to install it

- **WHEN** the staging action runs on a host where the tool venv does not exist
- **THEN** the flow warns, previews the plan that installs it, and stages nothing unless that plan is applied

#### Scenario: Cleaning an environment keeps the staging tool

- **WHEN** a migration environment that staged modules is cleaned
- **THEN** the shared staging-tool venv is untouched, because it sits beside the environments, not inside one

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

### Requirement: Reviewed module code is promoted to a location the operator owns

The staged code of a module at a step is the operator's own work — the migrator's mechanical output plus
every correction made by hand — and it lives inside the migration environment, which cleaning removes and
re-staging replaces. The system SHALL offer an action that **promotes** a module's reviewed code for one or
more steps to a durable location the operator names: one directory per version, outside any migration
environment.

Promotion SHALL **copy**, never move: the environment stays runnable, and a promotion can be discarded and
made again. It SHALL go through the standard plan → preview → apply flow, and SHALL require an exact-phrase
confirmation when it would replace code already promoted for that module and version, since that code may
carry review the environment's copy does not.

Where the durable location is a git repository, the system SHALL offer to commit the promotion on the branch
that names the version, using the **operator's** identity, hooks and signing configuration — it is their
history. This is the opposite of the throwaway repositories staging creates inside each stage directory,
which are deliberately insulated from that configuration, and the generated documentation SHALL say which is
which.

#### Scenario: A reviewed step is promoted

- **WHEN** the operator promotes `client_sales` for step 16.0
- **THEN** the module's 16.0 staged code is copied to the durable location's `16.0` directory, and the
  environment's copy is unchanged

#### Scenario: Replacing promoted code is confirmed first

- **WHEN** the operator promotes a module and version that has been promoted before
- **THEN** the action names that module and version, and promotes nothing unless the exact phrase is typed

### Requirement: Staging consumes what has been promoted

A migration is rehearsed several times and run once, and the final run must apply what was proven rather
than derive it again. For each module and step, staging SHALL take its input from the durable location when
that module has promoted code for that version, and SHALL derive from the previous step only when it has
none.

A step whose input was promoted SHALL NOT run the module migrator: the code is already at that version. The
staging report SHALL state, for every step, whether it was derived or taken from the promoted copy, because
a step that was not derived is a step whose warnings the operator will not see this run.

A chain with nothing promoted SHALL behave exactly as it does without this capability.

#### Scenario: The final run applies proven work

- **WHEN** every step of a module has been promoted and the operator stages it again
- **THEN** no migrator runs for that module, each step's code comes from the durable location, and the
  report says so per step

#### Scenario: A partly promoted module is completed

- **WHEN** a module has promoted code up to 16.0 and nothing beyond it
- **THEN** steps up to 16.0 are taken from the durable location and 17.0 onward are derived from them

### Requirement: Divergence between the environment and the promoted copy is reported

Promotion copies, so the two can drift: the operator keeps working in the environment, or edits the durable
copy directly. The staging report SHALL name, per module and version, whether the environment's code and the
promoted code differ, comparing **content** rather than timestamps — a `cp -a` and a `git checkout` both
preserve times that say nothing about content.

Neither copy SHALL be treated as authoritative: the report says they differ and names both paths, and the
operator decides.

#### Scenario: Work continued after a promotion

- **WHEN** a module is promoted for 16.0 and then edited again in the environment
- **THEN** the report names that module and version as diverged, and says which path holds which copy
