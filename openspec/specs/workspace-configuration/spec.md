# workspace-configuration Specification

## Purpose

Describes a per-client development workspace as a validated JSON profile, and derives every convention that follows from it — instance names, paths, ports, database user and each version's `addons_path` — so the same profile always produces the same workspace.

## Requirements

### Requirement: Workspace profile schema and loading

The system SHALL describe a workspace with a JSON profile that deserializes into a `WorkspaceConfig`
containing at least a `name`, a non-empty list of Odoo `versions`, and optional `addon_prefix`,
`http_port_base`, `db_host`, `db_port`, `db_user`, and optional OCA repository entries. Loading a profile
SHALL ignore unknown keys so that older profiles keep loading (forward-compatible), and SHALL round-trip
(load → serialize) without losing known fields.

#### Scenario: Load a minimal profile

- **WHEN** a profile containing only `{"name": "acme", "versions": ["18.0"]}` is loaded
- **THEN** a `WorkspaceConfig` is produced with `name = "acme"` and `versions = ["18.0"]`

#### Scenario: Unknown keys are ignored

- **WHEN** a profile contains an unrecognized key alongside known fields
- **THEN** the unknown key is ignored and all known fields load unchanged

### Requirement: Profile validation

The system SHALL validate a profile before it is used to generate or manage a workspace. The workspace `name`
MUST match `^[a-z][a-z0-9_]{0,31}$` (filesystem- and PostgreSQL-safe), at least one Odoo version MUST be
present, and every version MUST be a parseable Odoo version string (e.g. `18.0`). Validation failure SHALL
raise an error naming the offending field, and no filesystem changes SHALL occur.

#### Scenario: Reject an invalid workspace name

- **WHEN** a profile with `name = "Acme!"` is validated
- **THEN** validation fails with an error identifying the name, and nothing is generated

#### Scenario: Reject an unparseable version

- **WHEN** a profile with `versions = ["nope"]` is validated
- **THEN** validation fails with an error identifying the version

### Requirement: Deterministic derived conventions

The system SHALL derive workspace conventions deterministically from the profile. For each version the
instance name SHALL be `odoo<major><name>`, the per-instance venv SHALL be `.venv/odoo<major>`, and the config
file SHALL be `config/odoo<major>.conf`. The HTTP port for a version SHALL be `http_port_base + step * k`,
where `k` is the version's rank among the configured versions ordered by major and `step` is a fixed offset,
so ports never collide across versions in the same workspace.

#### Scenario: Instance naming

- **WHEN** deriving the instance for workspace `acme` and version `18.0`
- **THEN** the instance name is `odoo18acme`, the venv is `odoo18`, and the config is `odoo18.conf`

#### Scenario: Non-colliding per-version ports

- **WHEN** a workspace declares versions `17.0`, `18.0`, `19.0` with `http_port_base = 8069`
- **THEN** the assigned HTTP ports are distinct and ordered by major (e.g. 8069, 8079, 8089)

### Requirement: Composed addons_path

The system SHALL compose each instance's `addons_path`, in precedence order, from the workspace
`addons-custom` directory, the workspace `addons-oca` directory, and the version's `odoo/addons` in the shared
repo cache. The composed value MUST reference only paths inside the workspace or the shared cache.

#### Scenario: addons_path ordering

- **WHEN** the `odoo.conf` for an instance is rendered
- **THEN** its `addons_path` lists `addons-custom`, then `addons-oca`, then the shared `odoo/addons`, in that order

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
