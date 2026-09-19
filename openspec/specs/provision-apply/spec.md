# provision-apply Specification

## Purpose

Installs and configures what a supported Ubuntu host is missing to build Odoo from source — build dependencies, PostgreSQL with a development role, the patched wkhtmltopdf — and, each opt-in, rtlcss for right-to-left languages, the outbound firewall and the local mail capture. Everything is a previewed, confirmed, root-gated plan that refuses any host outside the support matrix.

## Requirements

### Requirement: Apply is root-gated and previewed

`provision apply` SHALL assemble the install/configure steps into a command plan, preview it, and run it only
after confirmation. Because the steps mutate the host, `apply` MUST require root/sudo and MUST refuse with a
clear message when not run with sufficient privileges, making no changes.

#### Scenario: Refuse without privileges

- **WHEN** `provision apply` is invoked without root/sudo
- **THEN** it reports that system changes require sudo and makes no changes

#### Scenario: Preview before mutation

- **WHEN** an apply is confirmed
- **THEN** the full command plan is shown and no command runs until the user confirms

### Requirement: Install Odoo build dependencies

`provision apply` SHALL install the system and build packages Odoo needs from source (compiler toolchain and
the headers backing lxml, Pillow, psycopg2, python-ldap, etc.), as an idempotent apt step.

#### Scenario: Build dependencies are installed

- **WHEN** the build dependencies are missing and apply runs
- **THEN** the plan includes an `apt-get install` of the documented package set

### Requirement: Install and configure PostgreSQL with a development role

`provision apply` SHALL install PostgreSQL, enable and start its service, and create a development login role
if it does not already exist, so a workspace's `odoo.conf` can connect. The role SHALL default to `odoo`, the
role workspaces and migration environments use by default. The role name MUST match
`^[a-z_][a-z0-9_]{0,62}$`; any other value SHALL be rejected before a plan is assembled. Creating an existing
role MUST be a no-op.

#### Scenario: Dev role created idempotently

- **WHEN** apply configures PostgreSQL and the dev role is absent
- **THEN** the plan creates the role; re-running apply with the role present makes no change to it

#### Scenario: Unsafe role rejected

- **WHEN** the operator enters `odoo'; DROP DATABASE x; --` as the development role
- **THEN** apply reports the invalid role and assembles no plan

### Requirement: Loopback trust for the development role only

`provision apply` SHALL give the development role a loopback (`127.0.0.1/32` and `::1/128`) `trust` line in
`pg_hba.conf`, so a workspace `odoo.conf` connects without a password, and SHALL put any blanket
`host all all <loopback> trust` line back to `scram-sha-256` — a blanket trust lets any local user connect
as the `postgres` superuser.

This SHALL be planned whenever the rules are not already in that shape, **including on a host that already
has PostgreSQL and the role**, since those hosts are exactly the ones a previous version left with a blanket
trust. A blanket trust SHALL be recognised by its **method, not its address**: any `host` or `hostnossl` rule for
every role whose method is `trust`, whatever address it names — including addresses that contain loopback
without naming it (`all`, `0.0.0.0/0`, `127.0.0.0/8`) and the `address netmask` form, and however the line
is indented. The role's own line SHALL be inserted *before* any rule for every role, since the first
matching rule wins, and the role SHALL be treated as trusted only when its line is **reached**, never merely
present.

When the file pulls in rules the tool cannot see (`include`, `include_if_exists`, `include_dir`), the state
SHALL be reported as unknown rather than as either answer.

The step SHALL fail rather than report success when it cannot place the line, whatever shape the file has,
and SHALL end by connecting as the role over loopback — `pg_hba.conf` is first-match-wins, so a line that is
present but shadowed by an earlier rule is not a narrowing.

Every probe behind these decisions is a tri-state, and an answer that could not be obtained SHALL be treated
as "do the work", never as "already done": a stopped server hides both the role and the file. Every planned
step SHALL be idempotent, so acting on an unknown costs a no-op.

#### Scenario: An already-provisioned host is narrowed

- **WHEN** apply runs on a host that has PostgreSQL, the role, and a blanket loopback `trust`
- **THEN** the plan contains the `pg_hba` narrowing even though nothing needs installing

#### Scenario: Nothing to narrow

- **WHEN** the role already has its loopback trust line and no blanket trust exists
- **THEN** no `pg_hba` command is planned

#### Scenario: The line cannot be placed

- **WHEN** the file has no rule the insertion can anchor to and the line cannot be appended
- **THEN** the step exits non-zero naming the file, rather than leaving the role unable to connect

#### Scenario: A trust spelled another way is still blanket

- **WHEN** `pg_hba.conf` trusts every role on `localhost`, on `all`, or on `0.0.0.0/0` rather than
  `127.0.0.1/32`
- **THEN** each of those lines is narrowed too, and the check does not report the host as already narrow

#### Scenario: A role line that is present but never reached

- **WHEN** the role's trust line sits below a rule for every role that matches the same connection
- **THEN** the check reports the role as not trusted, and apply inserts a line that is reached

#### Scenario: The role's line is shadowed by an earlier rule

- **WHEN** the role's trust line is added but an earlier rule matches the same loopback connection first
- **THEN** the closing connection check fails the step, instead of reporting a narrowing that does not work

#### Scenario: PostgreSQL installed but stopped

- **WHEN** apply runs on a host where PostgreSQL is installed, its service is down, and the role therefore
  cannot be probed
- **THEN** the plan starts the service and creates the role if missing, rather than reporting the host as
  already provisioned

### Requirement: Install the Odoo-recommended patched wkhtmltopdf verified by checksum

`provision apply` SHALL install the Odoo-recommended patched wkhtmltopdf 0.12.6 (the build Odoo recommends
from 15 on), downloading the pinned asset for the host codename and verifying its SHA-256 before installing.
A checksum mismatch MUST abort the install. 0.12.5, recommended for Odoo ≤ 14, is not provisioned. When no
verified asset is pinned for the host, apply SHALL say so instead of skipping it silently.

#### Scenario: Checksum mismatch aborts

- **WHEN** the downloaded wkhtmltopdf asset does not match its pinned SHA-256
- **THEN** the install step aborts and wkhtmltopdf is not installed

#### Scenario: Version follows the Odoo rule

- **WHEN** provisioning for Odoo 18 (≥ 15)
- **THEN** the planned wkhtmltopdf is the 0.12.6 patched build

### Requirement: Optional Node and rtlcss

`provision apply` SHALL offer, as an optional step, installing Node.js and the `rtlcss` package, which Odoo
uses only to mirror its CSS for right-to-left languages, so a host that does not need it is not forced to
install Node. The prompt SHALL say what it is for, and Node.js SHALL be installed without recommended
packages.

#### Scenario: Node + rtlcss is opt-in

- **WHEN** the user declines the optional rtlcss step
- **THEN** no Node.js or rtlcss install command is included in the plan

### Requirement: Supported Ubuntu releases only

`provision apply` SHALL target only the host releases the support matrix declares. On any other host —
including an apt-family host that is not one of those releases — it MUST refuse cleanly, naming the detected
release and the supported ones, before assembling or running any command.

#### Scenario: A supported release proceeds to the plan

- **WHEN** `provision apply` runs on one of the Ubuntu releases the matrix declares
- **THEN** it assembles and previews the plan as usual

#### Scenario: An unsupported host is refused before any command

- **WHEN** `provision apply` runs on a host that is not one of the declared releases
- **THEN** it refuses with a message naming the detected release and the supported ones, and makes no changes
