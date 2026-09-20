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

### Requirement: A step's success means the thing happened

Where a command can succeed without achieving what it was planned for, `provision apply` SHALL check the
outcome rather than the command's exit status:

- **wkhtmltopdf** SHALL be re-read from `PATH` after installing, and the step SHALL fail when the binary
  found there is not the patched build — an unpatched distribution one earlier on `PATH` would otherwise
  leave the step reporting success with Odoo's PDF reports still degraded;
- **the opt-in services** (the outbound firewall, the mail capture) SHALL have their state reported once the
  plan has run. `systemctl restart` returns as soon as a `Type=simple` unit is forked, so a daemon that
  exits a second later leaves every step reporting success; the firewall failing closed or not running at
  all are both states the operator must be told about.

#### Scenario: An unpatched wkhtmltopdf wins on PATH

- **WHEN** the patched package installs but another `wkhtmltopdf` earlier on `PATH` is the one found
- **THEN** the step fails, naming the binary it found

#### Scenario: A service that started and died

- **WHEN** the firewall's unit is started by the plan and its daemon exits immediately afterwards
- **THEN** the run reports the service as not running, instead of ending on "Provisioning applied" alone

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
trust. A blanket trust SHALL be recognised by its **method, not its address, and on every connection type**: any
`host`, `hostssl`, `hostnossl`, `hostgssenc` or `hostnogssenc` rule for every role whose method is `trust`,
whatever address it names — including addresses that contain loopback without naming it (`all`,
`0.0.0.0/0`, `127.0.0.0/8`) and the `address netmask` form, and however the line is indented. `hostssl` is
not a corner case: the supported host runs with `ssl = on` and libpq prefers TLS, so a `hostssl` record is
the one a loopback connection is matched against. The role's own line SHALL be inserted *before* any rule for every role, since the first
matching rule wins, and the role SHALL be treated as trusted only when its line is **reached**, never merely
present.

When the file holds rules the *rewriter* cannot read one line at a time — a record continued with a trailing
backslash, or rules pulled in through `include`, `include_if_exists` or `include_dir` — the step SHALL
refuse to rewrite it, naming what it cannot see. Narrowing the rules it can read while leaving the rest
would report a success that did not happen. (The **check** reads such a file through the server and reports
it like any other; it is the text rewriting that has the blind spot.)

The role's line SHALL be appended on a line of its own: a file with no final newline would otherwise have
its last record fused with the first inserted rule.

The step SHALL fail rather than report success when it cannot place the line, whatever shape the file has.

After reloading PostgreSQL it SHALL ask the server what rules it now has (`pg_hba_file_rules`) and fail on
any of these, naming the file and line — which may be a file the rewriter never saw:

1. the server reports a rule it could not parse. It then refused to load the file and is still running the
   previous rules, while the file on disk reads as narrowed. `pg_ctl reload` returns success either way, so
   nothing else in the plan would notice;
2. a TCP rule still trusts every role — unless that rule's own line quotes its fields, since `"all"` is a
   role literally named `all` and not the keyword;
3. a TCP trust rule names its roles by pattern (`/…`) or group (`+…`), which this step cannot rule out;
4. the first rule PostgreSQL matches for the development role is not the plain `host` trust rule the step
   added.

That check is written against a different source of truth than the text the step wrote, because every defect
this feature has had took the form of a step reporting a success that had not happened.

It SHALL then end by connecting as the role over loopback — `pg_hba.conf` is first-match-wins, so a line that is
present but shadowed by an earlier rule is not a narrowing.

Every probe behind these decisions is a tri-state, and an answer that could not be obtained SHALL be treated
as "do the work", never as "already done": a stopped server hides both the role and the file. Every planned
step SHALL be idempotent, so acting on an unknown costs a no-op.

The rewriter, the check and the verification SHALL agree on what *reaches* the role: a plain `host` rule
only. A rewriter that accepted another connection type would insert nothing and then fail a verification
that re-running cannot fix.

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

#### Scenario: A TLS rule is still a trust

- **WHEN** `pg_hba.conf` holds `hostssl all all 127.0.0.1/32 trust`
- **THEN** it is narrowed like any other blanket trust — it is the rule a loopback connection actually
  matches on a host with `ssl = on`

#### Scenario: A trust rule for the role on another connection type

- **WHEN** the role already has a `hostssl` trust rule and no plain `host` one
- **THEN** the step inserts its own plain `host` rule, rather than treating the existing one as the role's
  line and leaving the verification to fail

#### Scenario: A file whose rules cannot all be read is refused

- **WHEN** `pg_hba.conf` continues a record onto the next line, or pulls in rules with `include_dir`
- **THEN** the step exits non-zero naming what it cannot see, and leaves the file untouched

#### Scenario: A trust the rewriter could not reach is caught after the reload

- **WHEN** a rule trusting every role remains anywhere the server can see, the rewrite having missed it
- **THEN** the verification step fails naming that file and line, rather than reporting the host as narrowed

#### Scenario: A rule that PostgreSQL matches first is caught

- **WHEN** a rule naming every role, or the development role itself, precedes the added trust rule
- **THEN** the verification step fails naming that rule

#### Scenario: A rule naming roles by group is refused, not matched

- **WHEN** a `trust` rule names its roles by group (`+…`) or pattern (`/…`)
- **THEN** the pattern check refuses it, because the server reports the field verbatim and cannot say
  whether the development role is in it — the "matches first" check cannot answer for such a rule

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
