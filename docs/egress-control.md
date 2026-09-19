---
type: how-to
title: "Egress control and mail capture"
description: "Block every outbound connection by default with OpenSnitch, ask before allowing, and capture Odoo's mail in Mailpit."
audience: [developer]
updated: 2026-09-19
---

# Egress control and mail capture

Testing or migrating a copy of a production database is where a development host does real damage. Three
things go wrong:

- **Customers get mail.** Mail reaches real customers through the mail servers stored in that database, which
  take precedence over `odoo.conf`.
- **Real services get called.** A cron or an addon calls a payment provider, an e-invoicing platform, a bank or
  a carrier.
- **A mailbox gets emptied.** Fetchmail drains a real mailbox.

Odoo's own `neutralize` covers only the modules that ship a script for it, and only from Odoo 16. It never
covers a custom addon that calls out on its own. So `odoo_dwg` works at the **host** level instead:

| Piece | What it does |
|---|---|
| **OpenSnitch** — outbound firewall | Blocks every outbound connection that has no rule. When its window is open, it asks you first. Every decision is logged with the process, the full command line, the destination and the rule that decided. |
| **Mailpit** — mail capture | A local SMTP server with a web UI. Odoo's mail lands there to be read, and is never delivered. |

Both are optional. `provision apply` installs them after a preview and your confirmation.

## Install

```bash
sudo python3 -m odoo_dwg provision      # → "Apply (install what's missing)"
```

Answer **yes** to *Install or update the outbound firewall (OpenSnitch)?* and to *Install or update the local
mail capture (Mailpit)?*. Running it again is safe:
- a component already at the pinned version is only reconfigured;
- the tool's own rules are rewritten, and yours are never touched.

`provision check` reports both. It shows a warning if OpenSnitch is not running, or if its configuration has
drifted from the hardened values below.

### What gets installed

| Component | Version | From | Verified by |
|---|---|---|---|
| OpenSnitch daemon + UI | 1.8.0 | the project's GitHub release (Ubuntu's archive has 1.5.8) | SHA-512 from the release's maintainer-signed `readme.txt.asc` |
| Mailpit | 1.31.2 | the project's GitHub release | SHA-256 digest GitHub records for the asset (Mailpit publishes no checksum file) |

The pins live in `odoo_dwg/egress.py`. Check them with `python tools/verify_egress_pins.py` (see
[Keeping the versions current](#keeping-the-versions-current)).

## How OpenSnitch is configured

- **The service** (`opensnitchd`) filters in the kernel and always runs.
- **The window** (`opensnitch-ui`) is a separate program. The service connects to it when it is open.

The package's defaults do not match "block unless allowed". The tool changes these keys in
`/etc/opensnitchd/default-config.json` and leaves every other key as shipped:

| Setting | Shipped | Set to | Why |
|---|---|---|---|
| `DefaultAction` | `allow` | `deny` | Applies whenever the window is closed. `allow` would let every connection without a rule out. |
| `ProcMonitorMethod` | `ebpf` | `proc` | Measured on WSL: with `ebpf`, a process lost its identity after about a minute. Its rules stopped matching and its traffic fell through to the default. Odoo runs for hours. |
| `InterceptUnknown` | `false` | `true` | With `false`, a connection whose process cannot be found skips **every** rule, including localhost, and is silently denied. WSL's localhost relay is such a connection, so a Windows browser could not open Mailpit's UI. With `true` it goes through the rules: localhost is allowed, and anything else is denied **and logged**. |
| `Internal.FlushConnsOnStart` | `true` | `false` | Otherwise starting the service would cut every open connection, including your editor's. |
| `FwOptions.QueueBypass` | `true` | `false` | **Fail closed.** If the service crashes, nothing goes out until it comes back. systemd restarts it within 30 s (`Restart=always`), and a clean stop still restores the network (see [Turning it off](#turning-it-off-or-uninstalling)). Measured: during a crash even GitHub was unreachable, and it recovered on its own. |
| `Server.Loggers` | none | `syslog`, `rfc5424` | **Every decision goes to the system journal, with or without the window** (`journalctl -t opensnitch`, see [The permanent record](#the-permanent-record)). The service's own log file does not record decisions at its normal level. |

### The rules the tool installs

The rules live in `/etc/opensnitchd/rules/`. OpenSnitch evaluates them **in file-name order, and the first
match decides**.
- **The tool's own rules** are named `00-odwg-…` so that they come first, ahead of the package's `000-…` rules,
  yours, and the ones the window creates (`allow-always-…`, `deny-…`).
- **Re-running `provision`** rewrites only `00-odwg-*` files.

| Rule | Effect |
|---|---|
| `00-odwg-000-allow-localhost`, `…-localhost6` | Loopback: PostgreSQL, Mailpit, anything local |
| `00-odwg-001-allow-systemd-resolved`, `…-dns-resolvers` | DNS: the system resolver, and the `nameserver` entries in `/etc/resolv.conf` at install time |
| `00-odwg-002-allow-ntp` | Clock synchronisation (`systemd-timesyncd`) |
| `00-odwg-003-allow-vscode-server` | The VS Code server (`~/.vscode-server`), the editor this tool configures |
| `00-odwg-010-reject-odoo-external` | **Any process whose command line contains `odoo-bin`** (workspaces, migration steps, the shell) **can reach nothing but localhost** |
| `00-odwg-020-allow-dev-infrastructure` | Any process may reach GitHub (including `cli.github.com` and `*.githubusercontent.com`), PyPI, `*.astral.sh` (uv's Pythons), the Ubuntu archives and npm, so `git`, `gh`, `pip`, `uv`, `apt` and `npm` keep working. Odoo never reaches this rule, because `010` matches it first. |

Everything else is **asked about** when the window is open, and **denied** when it is closed.

**Not included:** no rule is shipped for AI assistants or other personal tools. If a tool you use needs the
network, allow it once from the window (see below). On WSL, that includes an assistant running inside the
distro.

## Using the window

### Opening it

- **On WSL:** open the Windows Start menu and search for **"OpenSnitch (<your distro>)"**. WSLg adds that entry
  when the package is installed, and the window opens like any Windows application.
- **From a terminal:** `opensnitch-ui &`.
- **On a Linux host without a desktop:** the service runs on its own and denies anything without a rule. To use
  a window from another machine, point the service at it. Set `"Server": {"Address": "<ip>:50051"}` in the
  daemon configuration, then run `opensnitch-ui --socket "[::]:50051"` on the machine that shows the window. One
  window can manage several machines ("nodes").

WSLg has no system tray. The window and the prompts work, but there is no tray icon.

### Tabs worth knowing

- **Events:** every connection, allowed or blocked, with its process, command line, destination and the rule
  that decided. This is where you see what Odoo tried to reach.
- **Rules:** view, edit, disable or delete rules. The tool's `00-odwg-…` rules appear here too. Edit those in
  code, not here, because `provision` rewrites them.
- **Nodes, Hosts, Procs, Addresses:** the same events, grouped.

### Answering a prompt

When a program without a rule tries to connect, a prompt shows the program, its command line and the
destination.

- **If you do not answer within 30 seconds**, the connection is denied. It is not remembered, so it asks again
  next time.
- **One prompt at a time.** While a prompt is open, other new connections wait, and their packets are dropped.
- **Choose the scope before clicking.** The prompt defaults to a rule on the *whole program*. **Deny
  `/usr/bin/curl` forever** blocks curl *everywhere*, including the downloads `provision` needs. Before
  answering, open the prompt's details and pick **"to this host"** (the destination) instead of **"from this
  executable"**, unless you really mean every connection of that program.
- **Pick the duration.** *once*, *30 s*, … *until restart*, or *forever*. Only *forever* writes a rule file. The
  others live in memory until the service restarts.

### Deleting or fixing a rule

In **Rules**, right-click a rule, then **Delete** or **Edit**. Or delete its JSON file from
`/etc/opensnitchd/rules/`; the service reloads on its own.

### Letting Odoo reach one external service

Sometimes Odoo must reach something on purpose, such as a payment provider's sandbox. The tool's rule rejects
every non-local Odoo connection, and it comes first. So the exception needs a rule whose **name sorts before
`00-odwg-`** and matches **both** Odoo and that destination. A `list` operator requires all of its items to
match. For example, `/etc/opensnitchd/rules/00-a-allow-odoo-stripe-sandbox.json`:

```json
{
  "created": "2026-01-01T00:00:00Z", "updated": "2026-01-01T00:00:00Z",
  "name": "00-a-allow-odoo-stripe-sandbox",
  "description": "Odoo may reach the Stripe test API only",
  "action": "allow", "duration": "always", "enabled": true, "precedence": true, "nolog": false,
  "operator": {
    "type": "list", "operand": "list", "data": "", "sensitive": false,
    "list": [
      {"type": "regexp", "operand": "process.command", "data": "odoo-bin", "sensitive": false, "list": []},
      {"type": "simple", "operand": "dest.host", "data": "api.stripe.com", "sensitive": false, "list": []}
    ]
  }
}
```

### The permanent record

Every connection decision is written to the **system journal**, whether or not the window is open. Each entry
carries:
- source, destination IP and host, port and protocol;
- PID, UID, the program's path, its full command line and working directory;
- `ARG1`, the action, and `ARG2`, the rule that decided. `ARG1="<nil>"` means no rule matched, so the default
  action (**deny**) applied.

```bash
journalctl -t opensnitch --since today                        # everything
journalctl -t opensnitch --since today | grep -E 'ARG1="(<nil>|deny|reject)"'   # what was blocked
journalctl -t opensnitch --since today | grep 'odoo-bin'      # what Odoo tried
```

OpenSnitch 1.8.0 always tags these entries `opensnitch`, and journald's own limits keep them bounded.
`/var/log/opensnitchd.log` is the service's diagnostic log. At the normal level it does **not** record
connection decisions.

### The window's event history

The window keeps its own history **in memory** by default (`file::memory:`), so it is lost when the window
closes. The journal above is the permanent record either way. To keep the window's history too:
1. Go to **Preferences → Database**.
2. Choose **File** and a path such as `~/.local/share/opensnitch/events.db`.
3. Enable purging older entries, for example after 7 days.

### Closing the window

Closing the window does **not** open the network. The service keeps running and denies anything without a
rule. Nothing is asked until you open the window again.

## Turning it off or uninstalling

```bash
sudo python3 -m odoo_dwg provision   # → "Outbound firewall and mail capture (on/off, uninstall)"
```

The menu shows whether each component is installed and on. It offers only the actions that apply, each
previewed and confirmed:

| Action | What it runs | Effect |
|---|---|---|
| Turn the outbound firewall **off** | `systemctl disable --now opensnitch` | Unrestricted network. It **stays off after a restart** until you turn it on. |
| Turn the outbound firewall **on** | `systemctl enable --now opensnitch` | Back to deny-by-default, now and at every start. |
| **Uninstall** the outbound firewall | turn it off, remove the tool's `00-odwg-*` rules, `apt-get purge --autoremove` of the two packages, unload the packet-queue kernel modules | Shows exactly which packages `apt` will remove, and asks you to type `UNINSTALL`. Your own rules in `/etc/opensnitchd/rules/` are kept. |
| Turn the mail capture off / on | `systemctl disable --now mailpit` / `enable --now` | While it is off, Odoo's connection to `127.0.0.1:1025` is refused, so mail is still never delivered. Captured mail is kept. |
| **Uninstall** the mail capture | turn it off, remove the unit, the binary and `/var/lib/mailpit` | Asks you to type `UNINSTALL`. Captured mail is deleted. |

The same by hand, for a quick pause:

```bash
sudo systemctl stop opensnitch    # unrestricted until the next start or reboot
sudo systemctl start opensnitch
```

A clean stop removes the service's firewall hooks. **If the service crashes**, outbound traffic stays blocked,
because it fails closed, until systemd restarts it (within 30 s). `sudo systemctl restart opensnitch` does it
at once.

## Mail capture

- **Reading captured mail:** open **<http://localhost:8025>** in your browser. On WSL, the Windows browser
  reaches it through WSL's localhost forwarding.
- **Which mail it gets:** Mailpit receives everything sent to `127.0.0.1:1025`. Every generated `odoo.conf`, for
  workspaces and for migration steps, sets `smtp_server = 127.0.0.1` and `smtp_port = 1025`.
- **If Mailpit is not running**, Odoo's connection is refused. Mail stays unsent and is never delivered anywhere
  else.
- **Storage:** the service is `mailpit.service`, bound to `127.0.0.1` only. It keeps its messages in
  `/var/lib/mailpit/`, so they survive restarts, and Mailpit prunes them to its default limit.

### A copied database still mails out: redirect it

A database copied from production keeps its **own mail servers** (`ir.mail_server`), and Odoo uses them instead
of `odoo.conf`. With OpenSnitch running, those connections are blocked. But the mail is then neither sent nor
visible. To see it in Mailpit, use **Manage workspace → Redirect a database's mail to Mailpit**, or the same
entry in the migration menu. For the database you name, it:

- points every mail server at `127.0.0.1:1025`, with no encryption, and clears its user and password;
- deactivates incoming mail servers (fetchmail), so no real mailbox is read or emptied.

It works on Odoo 12 to 19 and asks you to type `REDIRECT`. **Use it on rehearsal copies only.** A database going
back to production must keep its real servers.

## Live production migrations

When the migrated database **goes back to production**:
- **Do not** redirect its mail.
- **Do not** run `neutralize` on it.

Keep OpenSnitch running instead:
- **During the migration** (`odoo-bin` steps), every attempt to reach the outside is rejected and logged.
- **Before cutover,** review what the migration tried to reach:
  `journalctl -t opensnitch --since <start> | grep odoo-bin`.
- **At cutover,** start the migrated database on its production host. That host is not firewalled by this tool.

## WSL notes

- **`reject` waits.** It behaves like `deny` on WSL, because the WSL kernel is built without
  `CONFIG_INET_DIAG_DESTROY`, which OpenSnitch needs to close a socket at once. Blocking is identical, but Odoo
  waits for its own timeout (about 60 s for SMTP) instead of failing immediately.
- **Only WSL traffic is filtered.** OpenSnitch sees connections made inside the distro. Windows applications are
  not affected.

## Keeping the versions current

```bash
python tools/verify_egress_pins.py
```

It needs the network and never changes anything. It checks:

- **OpenSnitch:** the pinned SHA-512 values still match the pinned release's signed `readme.txt.asc`. If `gpg` is
  installed, it also verifies that file's signature. It reports whether a newer release exists.
- **Mailpit:** the pinned SHA-256 still matches the digest GitHub records for the pinned asset. It reports
  whether a newer release exists.

To move to a new release:

1. **Read its release notes.**
2. **For OpenSnitch:**
   1. Download the release's `readme.txt.asc` and the maintainer's key (`gustavo_iniguez_goia.asc`).
   2. Run `gpg --import`, then `gpg --verify readme.txt.asc`.
   3. Check the key's fingerprint against the one pinned in `odoo_dwg/egress.py`.
   4. Copy the `Checksums-Sha512` lines for the `amd64` daemon `.deb` and the UI `.deb`.
3. **For Mailpit:** read the asset's digest with
   `gh api repos/axllent/mailpit/releases/latest --jq '.assets[] | select(.name=="mailpit-linux-amd64.tar.gz") | .digest'`.
4. **Update the pins** in `odoo_dwg/egress.py`, then re-run `tools/verify_egress_pins.py`.
5. **Re-check the configuration.** Compare the new package's `default-config.json` with the hardened keys above.
   A renamed key would silently undo a setting.
6. **Re-run the acceptance on the reference host:**
   - the development tools work;
   - an unknown host is denied with the window closed;
   - Odoo is blocked after running for more than a minute;
   - Odoo's mail lands in Mailpit.
