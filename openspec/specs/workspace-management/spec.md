# workspace-management Specification

## Purpose

Maintains an existing workspace from its validated `workspace.json`: repair a venv, refresh the shared clones, add a version, refresh the generated files (changed files only, each previous version kept as a backup) and redirect a rehearsal database's mail to the local capture. Every action is previewed and confirmed, destructive ones need a phrase, and addons, venvs and databases are touched only by the action that names them.

## Requirements

### Requirement: Discover existing workspaces

The system SHALL discover existing workspaces by listing the directories under `<base>` (excluding the shared
`.repos` cache and dotted entries) and present them for selection in the management flow.

#### Scenario: List workspaces for management

- **WHEN** the user opens the manage flow and `<base>` contains `acme` and `beta` plus `.repos`
- **THEN** `acme` and `beta` are offered and `.repos` is not

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

### Requirement: Refresh an existing workspace's generated files

The system SHALL offer, for an existing workspace, an action that rewrites the files the generator produces
from the workspace's `workspace.json`:
- the per-version configs and run scripts;
- `setup_venv.sh`;
- `.vscode/*`;
- `odools.toml`;
- the README;
- the profile.

Only files whose content would change SHALL be written. An existing file that changes SHALL first be copied
to `<file>.bak-<date>`. The interpreter of each version SHALL be read from its venv's `pyvenv.cfg`, so the files
describe and rebuild the venvs as they are; a version without a venv SHALL get the default interpreter. The
action SHALL NOT touch addons, venvs, clones or databases, and SHALL be previewed and confirmed. **Add a
version** SHALL write files the same way.

#### Scenario: Up-to-date workspace

- **WHEN** the refresh runs on a workspace whose generated files already match the generator
- **THEN** it reports that every generated file is up to date and plans nothing

#### Scenario: Stale and hand-edited files

- **WHEN** a workspace's `launch.json` predates the current generator and its `odoo18.conf` was edited by hand
- **THEN** the plan copies each to its dated `.bak-<date>`, rewrites only those two files, and leaves every other file untouched

#### Scenario: Interpreters are preserved

- **WHEN** a workspace's Odoo 14 venv was built with `uv` Python 3.8 and a version is added or files are
  refreshed
- **THEN** the regenerated `setup_venv.sh` and README still build and describe Odoo 14 on `uv` Python 3.8
