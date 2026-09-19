## MODIFIED Requirements

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
