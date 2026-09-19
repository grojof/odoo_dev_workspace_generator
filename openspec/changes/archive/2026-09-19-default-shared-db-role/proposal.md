## Why

A generated workspace cannot connect to PostgreSQL on a freshly provisioned host. `provision apply` creates
the role `odoo` and migration environments use `odoo`, but a workspace's `db_user` defaults to the workspace
name, so an `acme` workspace writes `db_user = acme` for a role that does not exist. The normal path —
provision, generate, serve — fails until the operator creates another role with `sudo`. The per-workspace
role buys nothing in return: loopback is `trust`, so any local user can already connect as any role.

Reviewing the field also showed that neither `db_user` nor the role typed into `provision apply` is
validated, although the role is interpolated unquoted into SQL run as `postgres` and `db_user` is written
into a file through a shell heredoc — against the project rule to validate every operator-supplied value that
reaches a shell or SQL string.

## What Changes

- A workspace's `db_user` defaults to `odoo`, the role `provision apply` creates by default and migration
  environments use, declared once in `models.py` and read by all three. A profile that sets `db_user` keeps
  it; generated workspaces are unaffected because `workspace.json` already records the resolved role.
- `db_user` and the provisioning role are validated as plain PostgreSQL identifiers
  (`^[a-z_][a-z0-9_]{0,62}$`); anything else is rejected before a plan is built.
- No `dbfilter` is emitted. Consequence, accepted: Odoo lists the databases the connecting role owns, so the
  database selector of any workspace shows every development database, as it already did across the versions
  of one workspace.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `workspace-configuration`: the profile's `db_user` defaults to the shared development role and is
  validated.
- `provision-apply`: the development role is validated before any command is assembled.

## Impact

- Code: `odoo_dwg/models.py` (default role constant, validator, `normalize_defaults`, `validate`,
  `MigrationEnv`), `odoo_dwg/provisioning.py`, `odoo_dwg/workflows/provision.py`.
- Tests: `tests/test_models.py`, provisioning tests.
- Docs: `docs/configuration-reference.md`, `docs/workspace-layout.md`, `docs/provisioning.md`,
  `docs/roadmap.md`, `CHANGELOG.md`.
- Behavior change for new workspaces only; no migration of existing ones.
