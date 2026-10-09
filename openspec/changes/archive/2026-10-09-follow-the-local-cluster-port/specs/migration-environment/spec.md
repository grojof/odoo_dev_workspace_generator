## ADDED Requirements

### Requirement: A migration environment uses the host's own cluster

A migration environment SHALL default to the port of the host's own PostgreSQL cluster.

The port is chosen as the provision check chooses it. The read-only commands that take `--db-port`
(`migrate audit`, `migrate modules`, `mail check`, `neutralise check`) SHALL default to it too. A port given
explicitly SHALL be used as given.

#### Scenario: Read-only commands beside another distribution

- **WHEN** `neutralise check --database copy` runs without `--db-port` on a host whose only cluster listens on
  5433, while another distribution's server on 5432 has a database of the same name
- **THEN** it reads the database on 5433
