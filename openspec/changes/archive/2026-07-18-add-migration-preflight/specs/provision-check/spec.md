# provision-check Specification (delta)

## MODIFIED Requirements

### Requirement: Read-only host readiness report

The system SHALL provide a `provision check` that inspects the host and renders a capability table of
(capability, state, detail) where state is one of OK / MISSING / WARN / INFO, covering the package family,
the Odoo build dependencies, PostgreSQL, wkhtmltopdf, Node + rtlcss, the system Python, `uv` (migration
interpreters), and Docker (migration 12/13 fallback). `check` MUST NOT modify the host in any way.

#### Scenario: Report on a host missing prerequisites

- **WHEN** `provision check` runs on a host without PostgreSQL and without the build dependencies
- **THEN** it prints a table marking those capabilities MISSING and makes no changes to the host

#### Scenario: Report on a ready host

- **WHEN** every prerequisite is already present
- **THEN** every capability is reported OK and nothing is installed

## ADDED Requirements

### Requirement: Docker detection distinguishes binary, daemon, and images

The system SHALL report Docker as three distinct signals: the `docker` binary present, the daemon
responding (`docker info`), and the presence of the OpenUpgrade fallback images (`odoo:13.0` / `odoo:12.0`)
as an informational row. A permission failure talking to the daemon SHALL be reported distinctly from
Docker not being installed.

#### Scenario: Binary present, daemon unreachable

- **WHEN** `docker` is installed but `docker info` fails
- **THEN** the report marks the binary OK and the daemon not ready, including the error detail (e.g. permission or service down)
