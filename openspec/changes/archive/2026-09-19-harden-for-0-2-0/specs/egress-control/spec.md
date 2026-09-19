## MODIFIED Requirements

### Requirement: Owned baseline rules

`provision` SHALL write a baseline rule set named `00-odwg-<nnn>-<name>.json` and SHALL rewrite only files with
that prefix, leaving every other rule untouched. In evaluation order, the baseline SHALL:
1. allow localhost;
2. allow the host's non-loopback DNS resolvers, read from `/etc/resolv.conf` at apply time, and
   `systemd-resolved`;
3. allow `systemd-timesyncd`;
4. allow the VS Code server (`^/home/[^/]+/\.vscode-server/`);
5. reject every non-localhost connection from a process whose command line contains `odoo-bin`;
6. allow the development infrastructure by destination host: GitHub (including `cli.github.com` and
   `*.githubusercontent.com`), PyPI, `*.astral.sh`, the Ubuntu archives (including their country mirrors such as
   `es.archive.ubuntu.com`) and npm.

No rule SHALL name an AI assistant.

#### Scenario: Odoo cannot use the infrastructure rule

- **WHEN** an `odoo-bin` process connects to `github.com`
- **THEN** the Odoo rule matches before the infrastructure rule and the connection is rejected

#### Scenario: Development tools keep working

- **WHEN** `git fetch`, `pip`, `uv` or `apt-get update` run with the baseline in place
- **THEN** their connections to the listed hosts are allowed

#### Scenario: Operator rules survive

- **WHEN** `provision apply` runs again on a host where the operator created rules from the UI
- **THEN** only `00-odwg-*` files are rewritten and the operator's rules are unchanged
