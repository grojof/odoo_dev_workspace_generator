## ADDED Requirements

### Requirement: Shared development database role

A workspace profile's `db_user` SHALL default to the shared development role `odoo` — the role
`provision apply` creates by default and migration environments use — when the profile does not set it. A
profile that sets `db_user` SHALL keep that value. The resolved value SHALL be recorded in the generated
`workspace.json`, so managing an existing workspace never changes its role. `db_user` MUST match
`^[a-z_][a-z0-9_]{0,62}$`; otherwise validation SHALL fail naming the field and nothing SHALL be generated.

#### Scenario: Minimal profile uses the shared role

- **WHEN** a profile containing only `{"name": "acme", "versions": ["18.0"]}` is loaded and normalized
- **THEN** `db_user` is `odoo`, and each generated `odoo.conf` carries `db_user = odoo`

#### Scenario: Explicit role is kept

- **WHEN** a profile sets `db_user = "acme"`
- **THEN** `db_user` stays `acme` after normalization

#### Scenario: Reject an unsafe role

- **WHEN** a profile with `db_user = "odoo; DROP ROLE x"` is validated
- **THEN** validation fails with an error identifying `db_user`, and nothing is generated
