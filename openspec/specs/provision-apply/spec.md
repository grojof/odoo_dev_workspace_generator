# provision-apply Specification

## Purpose

Installs and configures what a supported Ubuntu host is missing to build Odoo from source — build dependencies, PostgreSQL with a development role, the patched wkhtmltopdf, and optionally Node — as a previewed, confirmed, root-gated plan that refuses any host outside the support matrix.

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

### Requirement: Install the Odoo-recommended patched wkhtmltopdf verified by checksum

`provision apply` SHALL install the Odoo-recommended patched wkhtmltopdf — version 0.12.5 for Odoo ≤ 14 and
0.12.6 for Odoo ≥ 15 — downloading the pinned asset for the host codename and verifying its SHA-256 before
installing; a checksum mismatch MUST abort the install.

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
