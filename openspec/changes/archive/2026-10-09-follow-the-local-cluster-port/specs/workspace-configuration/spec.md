## ADDED Requirements

### Requirement: A new workspace uses the host's own cluster

A workspace created without a profile file SHALL be given the port of the host's own PostgreSQL cluster as
its `db_port`, chosen as the provision check chooses it. A profile that states `db_port` SHALL keep it.

The generated README's `createdb` line SHALL name the workspace's port.

#### Scenario: Quick creation beside another distribution

- **WHEN** a workspace is created with "New (quick)" on a host whose only cluster listens on 5433
- **THEN** its profile and every `odoo.conf` carry `db_port = 5433`, and its README's `createdb` has `-p 5433`
