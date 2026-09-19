# Spec Delta

## MODIFIED Requirements

### Requirement: Shared read-only repo cache

The system SHALL maintain a shared repository cache under `<base>/.repos`, cloning each configured Odoo
version once with `git clone --depth 1 --branch <version> --single-branch` from `odoo/odoo`, and each
configured OCA repository once, the same way, on the matching version branch. The cache SHALL be reused across workspaces,
and generation SHALL NOT re-clone a repository that is already present.

The clone SHALL be shallow by default and without a profile option: a development workspace does not read the
branch history, which is most of a clone's size. The documentation SHALL state how to fetch the full history
(`git fetch --unshallow`) for whoever needs it, and refreshing the cache SHALL keep working on a shallow clone.

#### Scenario: Clone a version once

- **WHEN** generating a workspace whose version `18.0` is not yet in the cache
- **THEN** the plan includes `git clone --depth 1 --branch 18.0 --single-branch <odoo-url>
  <base>/.repos/odoo-18.0`

#### Scenario: OCA repositories are cloned the same way

- **WHEN** a workspace configures the OCA repository `web` for version `18.0`
- **THEN** the plan clones it with `--depth 1 --branch 18.0 --single-branch`

#### Scenario: Reuse an existing clone

- **WHEN** the shared cache already contains `odoo-18.0`, whether shallow or full
- **THEN** the plan contains no clone command for `18.0` and reuses the existing clone

#### Scenario: Refreshing a shallow clone

- **WHEN** the operator refreshes the shared repositories and a clone is shallow
- **THEN** the refresh advances it to the branch head the same way it does a full clone
