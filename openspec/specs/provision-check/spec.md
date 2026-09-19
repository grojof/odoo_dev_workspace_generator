# provision-check Specification

## Purpose

Reports, read-only and without ever prompting for a password, whether a host can build and run Odoo: its release against the supported list, the build dependencies, PostgreSQL (service, version against the matrix floor, development role), wkhtmltopdf, the optional rtlcss for right-to-left languages, `uv` and its interpreters, and the optional outbound firewall (OpenSnitch) and mail capture (Mailpit). It reports; it never changes the host.

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
- **THEN** no capability is reported MISSING, informational rows (the host interpreter, the optional
  components) are still shown, and nothing is installed

### Requirement: PostgreSQL readiness detection

The system SHALL detect whether PostgreSQL is installed, whether its service is running, whether a usable
development role exists, and which server version is installed, reporting each as a distinct signal in the
table. The probes SHALL never prompt for a password:
- the service state and server version come from `pg_lsclusters`, or `pg_isready`;
- the role is checked by connecting as it over loopback, then through `sudo -n`.

When the role cannot be checked that way, it SHALL be reported as unknown (WARN), not MISSING. The installed server version SHALL be compared against the minimum PostgreSQL the support matrix
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

#### Scenario: No sudo, no prompt

- **WHEN** the check runs as a user without passwordless sudo and cannot log in as the role
- **THEN** no password is asked for, and the role row is WARN saying it could not be checked

### Requirement: Loopback authentication reporting

The check SHALL report how loopback authentication is configured for the development role, reading
`pg_hba.conf` at the path the server reports. A blanket `host all all <loopback> trust` SHALL be reported as
a WARN naming what apply would do, a missing role trust line as INFO, and the narrowed state as OK. When the
file cannot be read — it is root-owned — the row SHALL say so rather than claim either state.

#### Scenario: Blanket trust is called out

- **WHEN** `pg_hba.conf` trusts every role over loopback
- **THEN** the row is WARN and says apply narrows it to the development role

#### Scenario: Unreadable pg_hba is not read as narrow

- **WHEN** the check runs as a user who cannot read `pg_hba.conf`
- **THEN** the row is WARN saying it could not be read, never OK

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
- whether OpenSnitch is installed and its service is running, and which hardened settings the running
  configuration does not have;
- whether Mailpit is installed and its service is running.

Both SHALL be reported as optional.

#### Scenario: Softened configuration is flagged

- **WHEN** OpenSnitch runs with `DefaultAction` set to `allow`
- **THEN** the check reports the setting and that it differs from the hardened `deny`
