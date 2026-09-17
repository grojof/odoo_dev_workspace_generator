# Spec Delta

## MODIFIED Requirements

### Requirement: Read-only host readiness report

The system SHALL provide a `provision check` that inspects the host and renders a capability table of
(capability, state, detail) where state is one of OK / MISSING / WARN / INFO, covering the host OS release,
the Odoo build dependencies, PostgreSQL (presence, service, development role, and server version against the
matrix floor), wkhtmltopdf, Node + rtlcss, the system Python, and `uv` (migration steps and out-of-range
workspace interpreters). `check` MUST NOT modify the host in any way.

#### Scenario: Report on a host missing prerequisites

- **WHEN** `provision check` runs on a host without PostgreSQL and without the build dependencies
- **THEN** it prints a table marking those capabilities MISSING and makes no changes to the host

#### Scenario: Report on a ready host

- **WHEN** every prerequisite is already present
- **THEN** every capability is reported OK and nothing is installed

## REMOVED Requirements

### Requirement: Docker detection distinguishes binary, daemon, and images

**Reason**: Nothing in the tool uses Docker any more. The Odoo 13 step, the only step that ever ran in a
container, now runs natively in a `uv` virtualenv, so reporting a container runtime would describe a
prerequisite this project no longer has.

**Migration**: None needed. A host that installed Docker for earlier versions of this tool can keep or remove
it freely; `provision check` simply stops mentioning it.
