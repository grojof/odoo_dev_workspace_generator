## Why

Testing and migrating copies of production databases is where a development host does real damage.
- **Real customers get mail.** The copied database's own mail servers take precedence over `odoo.conf`
  (`ir_mail_server.py`), so they can mail real customers.
- **Crons and addons call real services.** They can reach payment providers, e-invoicing platforms, banks and
  carriers.
- **Mailboxes get emptied.** Fetchmail can drain a real mailbox.

Odoo's `neutralize` covers only the modules that ship a script for it, only from Odoo 16, and never a
badly-written custom addon. What is wanted is host-level control in two parts:
- **Nothing leaves unless allowed.** Outbound traffic is denied by default, and anything new is asked about
  and logged.
- **Mail is seen but not delivered.** Mail can still be inspected without being sent.

A spike on the reference host (WSL Ubuntu 24.04, 2026-09-19) validated the community-standard tools for both:
**OpenSnitch**, the Linux application firewall with interactive prompts, and **Mailpit**, a local SMTP capture
with a web UI. It also found the defaults that must change for them to hold (see `design.md`).

## What Changes

- **`provision` can install and harden OpenSnitch**, optionally. It uses the upstream 1.8.0 `.deb` pinned by
  SHA-512 from the maintainer-signed checksum list, not Ubuntu's 1.5.8. The hardening:
  - deny by default, whether or not the UI is connected;
  - identify processes with `proc` rather than `ebpf`, which lost the identity of processes older than about
    one minute;
  - never flush existing connections on start;
  - fail closed if the daemon dies;
  - normal log level.
- **`provision` installs a baseline rule set**, prefixed `odwg-`, owned and refreshed by the tool, and never
  touching the operator's own rules:
  - localhost;
  - the host's DNS resolvers and NTP;
  - the VS Code server;
  - development infrastructure by destination: GitHub, PyPI, `uv`'s Python builds, the Ubuntu archives, the
    GitHub CLI apt repository and npm;
  - **Odoo (`odoo-bin`) denied everything but localhost**, ahead of the infrastructure rule, so Odoo can never
    use it.
- **`provision` can install Mailpit**, optionally. It uses the pinned upstream release verified by SHA-256 and
  runs as a system service bound to `127.0.0.1`: SMTP on `1025`, web UI on `8025`.
- **Generated configs send mail to Mailpit.** Workspace and migration `odoo.conf` files set
  `smtp_server = 127.0.0.1` and `smtp_port = 1025`. Without Mailpit the connection is refused, so mail never
  leaves.
- **New action: redirect a database's mail to Mailpit.** It serves rehearsal copies only:
  - every `ir.mail_server` is pointed at Mailpit and its credentials are cleared;
  - fetchmail servers are deactivated.
  
  It asks for a confirmation phrase, works on Odoo 12–19, and is never meant for a production cutover
  database.
- `provision check` reports OpenSnitch (installed, running, default action, method) and Mailpit.
- **Documentation:** a new `docs/egress-control.md` covering:
  - how it works;
  - starting, reopening and closing the UI;
  - reading blocks and adding rules, and choosing a destination-scoped rule over a process-wide one;
  - making the event history persistent;
  - pausing the firewall;
  - live-migration guidance;
  - updating the pinned versions.

## Capabilities

### New Capabilities

- `egress-control`: host outbound firewall (OpenSnitch) installation, hardening and the baseline rules.
- `mail-capture`: Mailpit installation, generated SMTP settings, and redirecting a database's mail servers.

### Modified Capabilities

- `provision-check`: reports OpenSnitch and Mailpit.
- `workspace-generation`: `odoo.conf` sends mail to the local capture.
- `migration-environment`: step configs send mail to the local capture.

## Impact

- **Code:**
  - `odoo_dwg/planners.py`: OpenSnitch, Mailpit and rules plans;
  - `odoo_dwg/templates.py`: rules, daemon config, systemd unit, SMTP keys;
  - `odoo_dwg/provisioning.py`, `odoo_dwg/system.py`: probes;
  - `odoo_dwg/workflows/provision.py`, `odoo_dwg/workflows/workspace.py`, `odoo_dwg/workflows/migration.py`;
  - `odoo_dwg/i18n.py`.
- **Tests:** planners, templates, provisioning, i18n.
- **Docs:** `docs/egress-control.md` (new), `docs/provisioning.md`, `docs/commands.md`, `docs/migration.md`,
  `docs/support-matrix.md` (pinned versions), README, CHANGELOG, roadmap.
- **Host:** installing either component is opt-in, previewed and confirmed. With OpenSnitch denying by
  default, any tool not covered by a rule is blocked until allowed from the UI. That is the intended behaviour
  and is documented.
