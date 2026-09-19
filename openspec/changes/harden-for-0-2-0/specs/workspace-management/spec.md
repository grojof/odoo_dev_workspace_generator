## MODIFIED Requirements

### Requirement: Manage-only operations act on existing resources with confirmation

The system SHALL provide manage-only operations on an existing workspace. At minimum:
- regenerate or repair a per-instance venv;
- refresh the shared repositories;
- add an Odoo version to the workspace.

Each operation:
- MUST act only on an already-existing workspace, whose `workspace.json` SHALL be validated as a profile
  before anything is planned;
- MUST assemble a previewed plan;
- MUST require confirmation before any host-mutating step, and explicit confirmation for a destructive one
  (e.g. removing and rebuilding a venv).

Adding a version SHALL leave the loaded profile unchanged until its plan has been applied.

#### Scenario: Regenerate a venv requires confirmation

- **WHEN** the user chooses to regenerate the `odoo18` venv of an existing workspace
- **THEN** the plan to remove and rebuild `.venv/odoo18` is previewed and runs only after explicit confirmation

#### Scenario: Add a version reuses the shared cache

- **WHEN** the user adds version `19.0` to an existing workspace and `19.0` is already in the shared cache
- **THEN** the plan adds `config/odoo19.conf` and the `.venv/odoo19` venv without re-cloning `19.0`

#### Scenario: A declined addition changes nothing

- **WHEN** the user adds version `19.0` and declines or fails the plan
- **THEN** the workspace's profile still lists only its previous versions, for every later action

#### Scenario: A manipulated profile is refused

- **WHEN** an existing workspace's `workspace.json` contains a version with shell syntax
- **THEN** management reports the invalid profile and plans nothing

#### Scenario: Management refuses a missing workspace

- **WHEN** a management operation targets a workspace name that does not exist under `<base>`
- **THEN** the operation reports the workspace is missing and makes no changes
