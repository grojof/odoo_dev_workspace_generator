# egress-control Specification

## Purpose

Keeps a development host from reaching the outside unless allowed, so that testing or migrating a copy of production can never mail customers or call real services. The outbound firewall (OpenSnitch) is optional, installed pinned and hardened: it denies by default, confines Odoo to localhost ahead of every other rule, lets the development tools reach their hosts, records every decision in the system journal, and can be turned off, turned on or uninstalled from `provision`.

## Requirements

### Requirement: Optional OpenSnitch installation, pinned and verified

`provision apply` SHALL offer, as an opt-in step, to install OpenSnitch from the upstream release packages.
The daemon and the UI SHALL be pinned by version and by the SHA-512 values from the maintainer-signed release
checksums, and a mismatch SHALL abort before installing. The service SHALL NOT start before the hardened
configuration and the baseline rules are in place.

#### Scenario: Checksum mismatch aborts

- **WHEN** a downloaded OpenSnitch package does not match its pinned SHA-512
- **THEN** the plan stops before any package is installed

#### Scenario: Nothing runs unconfigured

- **WHEN** OpenSnitch is installed by the plan
- **THEN** the service is started only after the hardened configuration and the rules have been written

### Requirement: Hardened daemon configuration

The daemon configuration written by `provision` SHALL set:
- `DefaultAction` to `deny`;
- `ProcMonitorMethod` to `proc`;
- `InterceptUnknown` to `true`, so that connections whose process cannot be found go through the rules and are
  logged, instead of being dropped silently;
- `Internal.FlushConnsOnStart` to `false`;
- `FwOptions.QueueBypass` to `false`;
- `LogLevel` to `2`;
- `Server.Loggers` to a local syslog logger in `rfc5424` format, so every connection decision reaches the
  system journal whether or not a UI is connected.

Every other key SHALL be left as the package ships it.

#### Scenario: Unruled traffic is denied with the UI closed

- **WHEN** no UI is connected and a process opens a connection that no rule matches
- **THEN** the connection is denied

#### Scenario: Long-running processes stay identified

- **WHEN** a process whose command line contains `odoo-bin` connects to an external host after running for
  more than a minute
- **THEN** the Odoo rule still matches it and the connection is blocked

### Requirement: Owned baseline rules

`provision` SHALL write a baseline rule set named `00-odwg-<nnn>-<name>.json` and SHALL rewrite only files with
that prefix, leaving every other rule untouched. In evaluation order, the baseline SHALL:
1. allow localhost;
2. allow the host's non-loopback DNS resolvers, read from `/etc/resolv.conf` at apply time, on port 53 only,
   and `systemd-resolved`;
3. allow `systemd-timesyncd`;
4. reject every connection from a process whose command line contains `odoo-bin`, except those the rules
   above already allow (loopback, and DNS to the host's resolvers on port 53). It SHALL sort ahead of every
   remaining allow rule, so none of them can match an Odoo process first;
5. allow the VS Code server (`^/home/[^/]+/\.vscode-server/`);
6. allow the development infrastructure by destination host: GitHub (including `cli.github.com` and
   `*.githubusercontent.com`), PyPI, `*.astral.sh`, the Ubuntu archives (including their country mirrors such as
   `es.archive.ubuntu.com`) and npm.

No rule SHALL name an AI assistant.

#### Scenario: Odoo cannot use the infrastructure rule

- **WHEN** an `odoo-bin` process connects to `github.com`
- **THEN** the Odoo rule matches before the infrastructure rule and the connection is rejected

#### Scenario: No allow rule precedes the Odoo rejection

- **WHEN** the baseline rule set is written
- **THEN** every rule sorting before the Odoo rejection is one that cannot match an `odoo-bin` process —
  the loopback and DNS destinations, and the `systemd-timesyncd` binary — so an `odoo-bin` process started
  by an allowed program is rejected all the same

#### Scenario: Development tools keep working

- **WHEN** `git fetch`, `pip`, `uv` or `apt-get update` run with the baseline in place
- **THEN** their connections to the listed hosts are allowed

#### Scenario: Operator rules survive

- **WHEN** `provision apply` runs again on a host where the operator created rules from the UI
- **THEN** only `00-odwg-*` files are rewritten and the operator's rules are unchanged

### Requirement: Turn off, turn on and uninstall

`provision` SHALL offer, for each installed component (OpenSnitch, Mailpit), to turn it off or on
persistently across restarts, and to uninstall it. Uninstalling SHALL require a confirmation phrase.
Uninstalling OpenSnitch SHALL:
- first show the packages `apt` would remove;
- then remove only the tool's own `00-odwg-*` rules, keeping the operator's.

Uninstalling Mailpit SHALL remove its unit, binary and captured mail.

#### Scenario: Turned off stays off

- **WHEN** the operator turns the outbound firewall off
- **THEN** the service is stopped and disabled, outbound traffic is unrestricted, and it stays off after a
  restart until turned on

#### Scenario: Uninstall keeps operator rules

- **WHEN** OpenSnitch is uninstalled on a host where the operator created rules
- **THEN** the packages are purged, the `00-odwg-*` rules are gone, and the operator's rule files remain

#### Scenario: Decisions are recorded without the UI

- **WHEN** no UI is connected and a connection is blocked
- **THEN** the decision, with its process, destination and rule, appears in the system journal under the
  `opensnitch` tag
