# provision-check Specification

## Purpose

Reports, read-only, whether a host can build and run Odoo: its release against the supported list, the build dependencies, PostgreSQL and its version against the matrix floor, wkhtmltopdf, the optional web toolchain, and the interpreters and container images the migration paths need. It reports; it never changes the host.

## Requirements

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

### Requirement: PostgreSQL readiness detection

The system SHALL detect whether PostgreSQL is installed, whether its service is running, whether a usable
development role exists, and which server version is installed, reporting each as a distinct signal in the
table. The installed server version SHALL be compared against the minimum PostgreSQL the support matrix
declares for the Odoo versions in play, and reported WARN when it is below that floor, naming both versions.

#### Scenario: PostgreSQL installed but no dev role

- **WHEN** PostgreSQL is running but the expected development role does not exist
- **THEN** the report marks PostgreSQL OK (running) and the dev role MISSING

#### Scenario: Server version below the matrix floor is flagged

- **WHEN** the installed PostgreSQL server is older than the floor the matrix declares for a version in play
- **THEN** the row is WARN and names the installed version, the required floor and the Odoo version requiring
  it

#### Scenario: Server version at or above the floor is OK

- **WHEN** the installed PostgreSQL server meets the floor for every version in play
- **THEN** the version row is OK and states the detected server version

### Requirement: wkhtmltopdf patched-build detection

The system SHALL detect the installed wkhtmltopdf version and whether it is the Odoo-recommended patched
build, reporting a plain (un-patched) distribution build as WARN because Odoo reports may be degraded.

#### Scenario: Un-patched wkhtmltopdf is flagged

- **WHEN** wkhtmltopdf is present but is the plain distribution build (not "with patched qt")
- **THEN** the report marks it WARN with a note that reports may be degraded

### Requirement: Supported host release detection

The system SHALL detect the host operating system and release from `/etc/os-release` and report it against
the host releases the support matrix declares. A host that is not one of those releases SHALL be reported as
unsupported — naming the detected release and the supported ones — rather than assumed usable, and `check`
SHALL still complete without error.

#### Scenario: A supported Ubuntu release is reported OK

- **WHEN** `provision check` runs on one of the Ubuntu releases the matrix declares
- **THEN** the host row is OK and names the detected release

#### Scenario: An unsupported host is reported, not assumed

- **WHEN** `provision check` runs on a host whose OS or release is not in the matrix — including an
  apt-family host such as Debian
- **THEN** the host row reports it as unsupported, names the detected release and the supported ones, and the
  check still completes without error

### Requirement: Egress control and mail capture readiness

`provision check` SHALL report, without changing anything:
- whether OpenSnitch is installed and its service is running, with its configured default action and
  process-monitor method, flagging any value that differs from the hardened configuration;
- whether Mailpit is installed and listening on `127.0.0.1:1025`.

Both SHALL be reported as optional.

#### Scenario: Softened configuration is flagged

- **WHEN** OpenSnitch runs with `DefaultAction` set to `allow`
- **THEN** the check reports the setting and that it differs from the hardened `deny`
