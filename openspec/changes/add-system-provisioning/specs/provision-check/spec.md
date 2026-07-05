## ADDED Requirements

### Requirement: Read-only host readiness report

The system SHALL provide a `provision check` that inspects the host and renders a capability table of
(capability, state, detail) where state is one of OK / MISSING / WARN, covering the package family, the Odoo
build dependencies, PostgreSQL, wkhtmltopdf, Node + rtlcss, and the system Python. `check` MUST NOT modify the
host in any way.

#### Scenario: Report on a host missing prerequisites

- **WHEN** `provision check` runs on a host without PostgreSQL and without the build dependencies
- **THEN** it prints a table marking those capabilities MISSING and makes no changes to the host

#### Scenario: Report on a ready host

- **WHEN** every prerequisite is already present
- **THEN** every capability is reported OK and nothing is installed

### Requirement: Package-family detection

The system SHALL detect the host package family from `/etc/os-release`. When the host is not part of the
Debian/Ubuntu (apt) family supported in this version, `check` SHALL report the family as unsupported rather
than assuming apt.

#### Scenario: Non-apt host is reported, not assumed

- **WHEN** `provision check` runs on a host whose `ID`/`ID_LIKE` is not in the Debian/Ubuntu family
- **THEN** it reports the package family as unsupported and still completes without error

### Requirement: PostgreSQL readiness detection

The system SHALL detect whether PostgreSQL is installed, whether its service is running, and whether a usable
development role exists, reporting each as a distinct signal in the table.

#### Scenario: PostgreSQL installed but no dev role

- **WHEN** PostgreSQL is running but the expected development role does not exist
- **THEN** the report marks PostgreSQL OK (running) and the dev role MISSING

### Requirement: wkhtmltopdf patched-build detection

The system SHALL detect the installed wkhtmltopdf version and whether it is the Odoo-recommended patched
build, reporting a plain (un-patched) distribution build as WARN because Odoo reports may be degraded.

#### Scenario: Un-patched wkhtmltopdf is flagged

- **WHEN** wkhtmltopdf is present but is the plain distribution build (not "with patched qt")
- **THEN** the report marks it WARN with a note that reports may be degraded
