# workspace-configuration Specification

## Purpose

Describes a per-client development workspace as a validated JSON profile, and derives every convention that follows from it — instance names, paths, ports, database user and each version's `addons_path` — so the same profile always produces the same workspace.

## Requirements

### Requirement: Workspace profile schema and loading

The system SHALL describe a workspace with a JSON profile that deserializes into a `WorkspaceConfig`
containing:
- a `name` and a non-empty list of Odoo `versions` (required);
- optional `http_port_base`, `db_host`, `db_port`, `db_user` and OCA repository entries.

Loading a profile SHALL ignore unknown keys, so that older profiles keep loading; a former `addon_prefix` key,
for example, is ignored. It SHALL round-trip (load → serialize) without losing known fields.

#### Scenario: Load a minimal profile

- **WHEN** a profile containing only `{"name": "acme", "versions": ["18.0"]}` is loaded
- **THEN** a `WorkspaceConfig` is produced with `name = "acme"` and `versions = ["18.0"]`

#### Scenario: Unknown keys are ignored

- **WHEN** a profile contains an unrecognized key alongside known fields
- **THEN** the unknown key is ignored and all known fields load unchanged

### Requirement: Profile validation

The system SHALL validate a profile before it is used to generate or manage a workspace. Every value that
reaches a path, a generated script or `odoo.conf` SHALL be checked:
- the `name` MUST match `^[a-z][a-z0-9_]{0,31}$`;
- at least one version MUST be present, and every version MUST be exactly one of the supported `NN.0`
  strings (12.0–19.0);
- every OCA repository name MUST match `^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$` and MUST NOT contain `..`;
- `db_host` MUST be a host name or an IP address;
- `db_port` MUST be an integer from 1 to 65535, and `http_port_base` an integer from 1 to 64000;
- `db_user` MUST be a plain PostgreSQL role.

A malformed value, including one of the wrong JSON type, SHALL be reported as a validation error naming the
field, never raised as a crash. No filesystem change SHALL occur.

#### Scenario: Reject an invalid workspace name

- **WHEN** a profile with `name = "Acme!"` is validated
- **THEN** validation fails with an error identifying the name, and nothing is generated

#### Scenario: Reject an unparseable version

- **WHEN** a profile with `versions = ["nope"]` is validated
- **THEN** validation fails with an error identifying the version

#### Scenario: Reject a version carrying shell syntax

- **WHEN** a profile lists `18.0$(touch /tmp/p)`, `18` or `20.0` as a version
- **THEN** validation fails naming the version, and no script or config is written

#### Scenario: Reject path traversal and odoo.conf injection

- **WHEN** a profile has an OCA repository `../../etc`, or a `db_host` containing a newline
- **THEN** validation fails naming that field

### Requirement: Deterministic derived conventions

The system SHALL derive workspace conventions deterministically from the profile. For each version the
instance name SHALL be `odoo<major><name>`, the per-instance venv SHALL be `.venv/odoo<major>`, and the config
file SHALL be `config/odoo<major>.conf`. The HTTP port for a version SHALL be `http_port_base + step * k`,
where `k` is the version's rank among the configured versions ordered by major and `step` is a fixed offset,
so ports never collide across versions in the same workspace. Each instance SHALL also get a bus port
derived from its own HTTP port by a fixed offset, so bus ports cannot collide either, written under the key
that version's Odoo reads — `longpolling_port` up to Odoo 15, `gevent_port` from Odoo 16.

#### Scenario: Instance naming

- **WHEN** deriving the instance for workspace `acme` and version `18.0`
- **THEN** the instance name is `odoo18acme`, the venv is `odoo18`, and the config is `odoo18.conf`

#### Scenario: The bus port key follows the version

- **WHEN** the configs for `15.0` and `18.0` of the same workspace are rendered
- **THEN** the first sets `longpolling_port` and the second `gevent_port`, each a fixed offset above its
  own HTTP port, and the two values differ

#### Scenario: Non-colliding per-version ports

- **WHEN** a workspace declares versions `17.0`, `18.0`, `19.0` with `http_port_base = 8069`
- **THEN** the assigned HTTP ports are distinct and ordered by major (e.g. 8069, 8079, 8089)

### Requirement: Composed addons_path

The system SHALL compose each instance's `addons_path`, in precedence order, from the workspace
`addons-custom` directory, the per-version symlink of each configured OCA repository under
`addons-oca/odoo<major>/`, and the version's `odoo/addons` in the shared repo cache. The composed value MUST
reference only paths inside the workspace or the shared cache.

#### Scenario: addons_path ordering

- **WHEN** the `odoo.conf` for an instance with one OCA repository is rendered
- **THEN** its `addons_path` lists `addons-custom`, then `addons-oca/odoo<major>/<repo>`, then the shared
  `odoo/addons`, in that order

#### Scenario: A workspace without OCA repositories

- **WHEN** the profile configures no OCA repository
- **THEN** the `addons_path` holds the custom directory and the core add-ons only, with no `addons-oca` entry

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
