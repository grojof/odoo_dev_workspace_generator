# migration-environment Specification Delta

## ADDED Requirements

### Requirement: A source database can be seeded from demo data

A rehearsal requires a source dump, which before a client's database exists nobody has. The system SHALL be
able to build a database at the chain's **source** version, with Odoo's demo data and a chosen set of
modules, and to dump it in the format the driver requires (`pg_dump -Fc`) into the environment, so that the
chain can then be run exactly as it would be on a client's dump.

The action SHALL refuse to overwrite an existing source dump without the operator saying so, because the
dump a chain's checkpoints were taken against is not replaceable silently.

Module installation SHALL be reported per module: a module that fails to install SHALL be named, and SHALL
NOT leave the action reporting a seeded database.

A module name given by the operator MUST be a valid Odoo module name before it reaches a command line;
otherwise the action SHALL stop naming the value.

#### Scenario: A chain rehearsed with no client data

- **WHEN** the operator seeds a 12.0 source database with demo data and runs the driver against the dump it
  produced
- **THEN** the chain runs as it would on a client's dump, through the same checkpoints

#### Scenario: A module that will not install

- **WHEN** one of the chosen modules fails to install at the source version
- **THEN** it is named and the action does not report a seeded database

#### Scenario: An existing dump is not replaced by accident

- **WHEN** the environment already holds a source dump
- **THEN** the action says so and does not overwrite it unless the operator confirms
