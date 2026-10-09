## ADDED Requirements

### Requirement: The check probes the host's own cluster

The check SHALL probe PostgreSQL on the port of the host's own cluster, read from `pg_lsclusters`.

When the host has exactly one cluster its port is used, online or not; with several, the one online when
exactly one is; otherwise 5432. A server answering on loopback that is not one of the host's clusters — on
WSL 2, another distribution's — SHALL NOT be taken for the host's. The report SHALL name the port it probed.

#### Scenario: A cluster on 5433 beside another distribution's server

- **WHEN** the host's only cluster listens on 5433 and another distribution's server answers on 5432
- **THEN** the check reports PostgreSQL running on 5433, and checks the role and the loopback rules there
