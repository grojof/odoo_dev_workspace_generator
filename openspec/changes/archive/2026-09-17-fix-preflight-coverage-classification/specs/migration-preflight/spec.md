# Spec Delta

## MODIFIED Requirements

### Requirement: Per-step addons coverage

For every module installed in the database, the preflight SHALL verify that each step of the chain can find
the module somewhere in that step's `addons_path` (target core, OpenUpgrade, the environment's per-version
OCA dir, or the per-version custom dir).

Before reporting a module as missing, the check SHALL consult that step's OpenUpgrade checkout for the
renames and merges it declares, and SHALL treat a module whose declared successor resolves in that step's
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
- **THEN** it aborts non-zero before restoring or upgrading anything, naming the module, the step and the
  directory to fill
