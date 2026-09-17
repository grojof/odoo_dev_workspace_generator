# provision-check Specification

## Purpose

Reports, read-only, whether a host can build and run Odoo: its release against the supported list, the build dependencies, PostgreSQL and its version against the matrix floor, wkhtmltopdf, the optional web toolchain, and the interpreters and container images the migration paths need. It reports; it never changes the host.

## Requirements
### Requirement: Read-only host readiness report

The system SHALL provide a `provision check` that inspects the host and renders a capability table of
(capability, state, detail) where state is one of OK / MISSING / WARN / INFO, covering the host OS release,
the Odoo build dependencies, PostgreSQL (presence, service, development role, and server version against the
matrix floor), wkhtmltopdf, Node + rtlcss, the system Python, `uv` (migration and out-of-range workspace
interpreters), and Docker (migration 12/13 fallback). `check` MUST NOT modify the host in any way.

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

### Requirement: Docker detection distinguishes binary, daemon, and images

The system SHALL report Docker as three distinct signals: the `docker` binary present, the daemon
responding (`docker info`), and the presence of the OpenUpgrade fallback images (`odoo:13.0` / `odoo:12.0`)
as an informational row. A permission failure talking to the daemon SHALL be reported distinctly from
Docker not being installed.

#### Scenario: Binary present, daemon unreachable

- **WHEN** `docker` is installed but `docker info` fails
- **THEN** the report marks the binary OK and the daemon not ready, including the error detail (e.g. permission or service down)

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
