# workspace-management Specification

## Purpose
TBD - created by archiving change add-workspace-generation. Update Purpose after archive.
## Requirements
### Requirement: Discover existing workspaces

The system SHALL discover existing workspaces by listing the directories under `<base>` (excluding the shared
`.repos` cache and dotted entries) and present them for selection in the management flow.

#### Scenario: List workspaces for management

- **WHEN** the user opens the manage flow and `<base>` contains `acme` and `beta` plus `.repos`
- **THEN** `acme` and `beta` are offered and `.repos` is not

### Requirement: Manage-only operations act on existing resources with confirmation

The system SHALL provide manage-only operations on an existing workspace — at minimum: regenerate/repair a
per-instance venv, refresh the shared repositories, and add an Odoo version to the workspace. Each operation
MUST act only on an already-existing workspace, MUST assemble a previewed plan, and MUST require confirmation
before any host-mutating step; a destructive step (e.g. removing and rebuilding a venv) MUST require an
explicit confirmation.

#### Scenario: Regenerate a venv requires confirmation

- **WHEN** the user chooses to regenerate the `odoo18` venv of an existing workspace
- **THEN** the plan to remove and rebuild `.venv/odoo18` is previewed and runs only after explicit confirmation

#### Scenario: Add a version reuses the shared cache

- **WHEN** the user adds version `19.0` to an existing workspace and `19.0` is already in the shared cache
- **THEN** the plan adds `config/odoo19.conf` and the `.venv/odoo19` venv without re-cloning `19.0`

#### Scenario: Management refuses a missing workspace

- **WHEN** a management operation targets a workspace name that does not exist under `<base>`
- **THEN** the operation reports the workspace is missing and makes no changes

