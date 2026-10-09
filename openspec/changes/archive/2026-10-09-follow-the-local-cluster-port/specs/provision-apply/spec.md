## ADDED Requirements

### Requirement: The connection check targets the server apply configured

Apply's loopback connection check SHALL connect to the port of the server it created the role in, read from
that server at run time (`SHOW port`), never to PostgreSQL's default port.

#### Scenario: Another server holds 5432

- **WHEN** apply configures a cluster on 5433 while another distribution's server answers on 5432
- **THEN** the check connects on 5433, and fails if the role cannot connect there, whatever 5432 answers
