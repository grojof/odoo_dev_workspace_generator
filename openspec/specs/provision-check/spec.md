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
- the service state comes from `pg_lsclusters`, else `pg_isready`, which answers *running*, not *which*;
  the server version comes from `pg_lsclusters`, else `SHOW server_version` through a non-prompting `sudo`;
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

The check SHALL report how loopback authentication is configured for the development role, reading the rules
**from the server** (`pg_hba_file_rules`) rather than parsing `pg_hba.conf`. PostgreSQL's own parse folds
continued records, expands `include`, `include_if_exists` and `include_dir`, splits list-valued fields, and
names the file each rule came from — so a rule this tool could not previously see is reported like any
other.

A blanket trust — any TCP rule (`host`, `hostssl`, `hostnossl`, `hostgssenc`, `hostnogssenc`) whose **role
field is the keyword `all`** and whose method is `trust`, **on any database** and whatever address it names
— SHALL be reported as a WARN naming what apply would do; a role whose trust rule is not the one a
connection **reaches** as INFO; and the narrowed state as OK. The database field bounds which database is
exposed, never whether it is: a rule trusting every role on one database lets any local user connect to it
as `postgres`, and a superuser in one database is a superuser on the host.

A rule whose own line quotes **its role field** SHALL NOT be treated as a blanket trust: `"all"` is a role
literally named `all`, which the view reports exactly like the keyword and which PostgreSQL does not match
a connection against. The exception SHALL be that field only — a quote elsewhere on the line, an address
written `"127.0.0.1/32"` included, leaves the rule a blanket trust, because the server reads it as one.

When the state cannot be had — PostgreSQL is not running, the view cannot be read without a password, the
server reports a rule it could not parse, or a TCP trust rule names its roles by pattern (`/…`) or group
(`+…`), which cannot be told to cover every role — the row SHALL say so rather than claim either state.

A role SHALL be treated as reached only through a plain `host` rule: the supported host runs with `ssl = on`
and clients prefer TLS, so a `hostnossl` rule is never consulted, and calling one "reached" would report a
host as narrowed where the role cannot connect at all.

#### Scenario: Blanket trust is called out

- **WHEN** `pg_hba.conf` trusts every role over loopback
- **THEN** the row is WARN and says apply narrows it to the development role

#### Scenario: A trust for one database is still a trust

- **WHEN** `pg_hba.conf` holds `host mydb all 127.0.0.1/32 trust`
- **THEN** the row is WARN, because any local user may then connect to `mydb` as `postgres`

#### Scenario: A trust in an included file is seen

- **WHEN** the blanket trust lives in a file pulled in with `include_dir`
- **THEN** the row reports it, because the server resolves the include

#### Scenario: A role line that is never reached is not narrow either

- **WHEN** the role's trust rule sits below a rule that matches the same connection
- **THEN** the row does not report the host as narrowed

#### Scenario: The state cannot be had

- **WHEN** PostgreSQL is not running, or the view cannot be read without a password
- **THEN** the row says so, never OK

#### Scenario: A role literally named all is not the keyword

- **WHEN** a rule reads `host all "all" 127.0.0.1/32 trust`
- **THEN** it is not reported as a blanket trust, because PostgreSQL does not match a connection against a
  quoted role field

#### Scenario: A quote somewhere else does not excuse the rule

- **WHEN** a rule reads `host all all "127.0.0.1/32" trust`
- **THEN** it is reported as a blanket trust, because the server accepts that connection like any other

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
