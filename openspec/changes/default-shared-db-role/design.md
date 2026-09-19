## Context

Three places name a PostgreSQL role: `provision apply` (asks, default `odoo`), `MigrationEnv.db_user`
(`odoo`) and `WorkspaceConfig.normalize_defaults` (the workspace name). Only the last disagrees, and it is the
one a new user meets first. Loopback authentication is `trust` by design (`docs/provisioning.md`).

## Goals / Non-Goals

**Goals:** provision → generate → serve works with no extra role; the default is declared once; every role
value reaching SQL or a shell is validated.

**Non-Goals:** per-client database isolation, `dbfilter`, password authentication, changing existing
workspaces.

## Decisions

- **One shared development role, `odoo`, as `DEFAULT_DB_ROLE` in `models.py`.** The provisioning prompt,
  `ProvisionFacts`, `gather_facts` and `MigrationEnv` read it instead of repeating the literal.
  *Alternative:* keep a role per workspace and create it during generation — rejected: generation would need
  `sudo`, which only `provision apply` asks for, and the separate role isolates nothing under `trust`.
- **No `dbfilter`.** Odoo's `list_dbs` (`odoo/service/db.py`) lists databases owned by the connecting role,
  so with one role every workspace's selector lists every development database. A `dbfilter = ^<name>` would
  hide them but force a naming convention on every database. *Accepted trade-off*, already true between the
  versions of one workspace, and harmless on a local development host.
- **Validate roles as unquoted PostgreSQL identifiers**, `^[a-z_][a-z0-9_]{0,62}$` (lowercase because
  unquoted identifiers fold to it; 63 bytes is `NAMEDATALEN - 1`). Checked in `WorkspaceConfig.validate` and
  in `provision apply` before facts are gathered, so a bad value never reaches `plan_postgresql`.

## Risks / Trade-offs

- A hand-written profile without `db_user`, re-applied to a workspace that was generated under the old
  default, would now write `db_user = odoo`. → Negligible: generation records the resolved `db_user` in
  `workspace.json`, which is what management reads; the changelog names the change.
- Databases of different clients share an owner. → Dropping is always by explicit name (`dropdb "$DB"`),
  never by owner, so nothing is removed across workspaces.
