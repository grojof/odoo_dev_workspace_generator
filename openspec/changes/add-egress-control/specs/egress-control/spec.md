## ADDED Requirements

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
- `Internal.FlushConnsOnStart` to `false`;
- `FwOptions.QueueBypass` to `false`;
- `LogLevel` to `2`.

Every other key SHALL be left as the package ships it.

#### Scenario: Unruled traffic is denied with the UI closed

- **WHEN** no UI is connected and a process opens a connection that no rule matches
- **THEN** the connection is denied

#### Scenario: Long-running processes stay identified

- **WHEN** a process whose command line contains `odoo-bin` connects to an external host after running for
  more than a minute
- **THEN** the Odoo rule still matches it and the connection is blocked

### Requirement: Owned baseline rules

`provision` SHALL write a baseline rule set named `odwg-<nnn>-<name>.json` and SHALL rewrite only files with
that prefix, leaving every other rule untouched. In evaluation order, the baseline SHALL:
1. allow localhost;
2. allow the host's non-loopback DNS resolvers, read from `/etc/resolv.conf` at apply time, and
   `systemd-resolved`;
3. allow `systemd-timesyncd`;
4. allow the VS Code server (`^/home/[^/]+/\.vscode-server/`);
5. reject every non-localhost connection from a process whose command line contains `odoo-bin`;
6. allow the development infrastructure by destination host: GitHub (including `cli.github.com` and
   `*.githubusercontent.com`), PyPI, `*.astral.sh`, the Ubuntu archives and npm.

No rule SHALL name an AI assistant.

#### Scenario: Odoo cannot use the infrastructure rule

- **WHEN** an `odoo-bin` process connects to `github.com`
- **THEN** the Odoo rule matches before the infrastructure rule and the connection is rejected

#### Scenario: Development tools keep working

- **WHEN** `git fetch`, `pip`, `uv` or `apt-get update` run with the baseline in place
- **THEN** their connections to the listed hosts are allowed

#### Scenario: Operator rules survive

- **WHEN** `provision apply` runs again on a host where the operator created rules from the UI
- **THEN** only `odwg-*` files are rewritten and the operator's rules are unchanged
