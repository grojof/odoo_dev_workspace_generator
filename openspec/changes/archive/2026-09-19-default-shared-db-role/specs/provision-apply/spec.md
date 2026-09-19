## MODIFIED Requirements

### Requirement: Install and configure PostgreSQL with a development role

`provision apply` SHALL install PostgreSQL, enable and start its service, and create a development login role
if it does not already exist, so a workspace's `odoo.conf` can connect. The role SHALL default to `odoo`, the
role workspaces and migration environments use by default. The role name MUST match
`^[a-z_][a-z0-9_]{0,62}$`; any other value SHALL be rejected before a plan is assembled. Creating an existing
role MUST be a no-op.

#### Scenario: Dev role created idempotently

- **WHEN** apply configures PostgreSQL and the dev role is absent
- **THEN** the plan creates the role; re-running apply with the role present makes no change to it

#### Scenario: Unsafe role rejected

- **WHEN** the operator enters `odoo'; DROP DATABASE x; --` as the development role
- **THEN** apply reports the invalid role and assembles no plan
