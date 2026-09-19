## Context

A spike on the reference host (WSL Ubuntu 24.04, kernel 6.6.87.2-microsoft-standard-WSL2, WSL 2.5.9, 2026-09-19)
installed OpenSnitch 1.8.0 and Mailpit 1.31.2, then drove a real Odoo 18 through three cases:
- mail to Mailpit;
- mail through a production-like mail server stored in the database;
- an external API call.

Every decision below comes from what that spike measured. Nothing here is assumed.

**What the host provides.**
- The WSL kernel ships nftables, NFQUEUE (`nfnetlink_queue` loads as a module), `xt_owner` and eBPF, so
  OpenSnitch runs.
- WSLg is present (`DISPLAY=:0`, a Wayland socket), so the Qt UI opens as a Windows window. WSLg also adds the
  package's `.desktop` entry to the Windows Start menu as **"OpenSnitch (<distro>)"**.
- WSLg has no system tray. Qt warns about it, but the main window and the prompts work.

## Goals / Non-Goals

**Goals.**
- Default-deny outbound on the whole host, with ask-then-allow when the UI is open and deny when it is not.
- A log of every decision.
- Mail inspected but never delivered.
- Everything installed, hardened and documented by `provision`, opt-in, previewed and confirmed.

**Non-Goals.**
- A firewall of our own.
- Odoo's `neutralize`: it depends on the version and on modules shipping scripts.
- Filtering Windows-side traffic.
- Emitting rules for any AI assistant (project principle). The operator allows their own tools from the UI.

## Decisions

### OpenSnitch, installed from upstream and pinned

- **Source.** Upstream `opensnitch_1.8.0-1_amd64.deb` and `python3-opensnitch-ui_1.8.0-1_all.deb`. Ubuntu's
  archive carries 1.5.8.
- **Verification.** Pinned by the SHA-512 values from the release's `readme.txt.asc`. That file is signed by the
  maintainer (Gustavo Iñiguez Goya, EdDSA key `858F918F2887BD809F08DDDB6CD595FEFD12DAE2`); the signature and
  both digests were verified in the spike.
- **Pattern.** The same as wkhtmltopdf: pinned facts in code, and the update procedure documented, including
  re-verifying the signature.
- **Install.** `apt-get install` of the two files, with `policy-rc.d` preventing the service from starting
  before our configuration is in place.

### Hardening: the defaults that do not hold, as measured

| Key | Package default | Ours | Why (measured) |
|---|---|---|---|
| `DefaultAction` | `allow` | `deny` | With the UI closed, the daemon falls back to its own action. `allow` lets everything unruled out, the opposite of the goal. The UI's own default is deny, with a 30 s prompt timeout. |
| `ProcMonitorMethod` | `ebpf` | `proc` | With `ebpf`, a process lost its identity after about one minute. A rule on `odoo-bin` stopped matching and the connection fell through to the default, reproduced with a process that waited 70 s. With `proc` the same test stayed blocked. Odoo is a long-running process. |
| `Internal.FlushConnsOnStart` | `true` | `false` | Starting the daemon would cut every open connection, including the editor's and any remote session. |
| `FwOptions.QueueBypass` | `true` | `false` | `true` accepts packets when the daemon is not reading the queue, which fails open. `false` fails closed. A clean `systemctl stop` removes the daemon's rules and restores the network, which is the documented way to pause. A crash leaves traffic blocked until the daemon restarts. |
| `LogLevel` | `2` | `2` | The spike raised it to debug to diagnose. Normal operation keeps it at 2. |

### Rules: an owned baseline, never touching the operator's

- **Ownership.** Rule files are written as `/etc/opensnitchd/rules/odwg-<nnn>-<name>.json`. `provision`
  rewrites only `odwg-*`. Rules created from the UI keep the UI's own names and are never modified.
- **Order.** Rules are evaluated alphabetically, and `precedence: true` makes the first match final, so the
  numbering is the policy:
  1. `odwg-000` **localhost**: IPv4 loopback and `::1`.
  2. `odwg-001` **DNS resolvers**: each non-loopback `nameserver` in `/etc/resolv.conf`, read at apply time
     (`10.255.255.254` on WSL), plus `systemd-resolved`.
  3. `odwg-002` **NTP**: `systemd-timesyncd`.
  4. `odwg-003` **VS Code server**: `process.path` matches `^/home/[^/]+/\.vscode-server/`. It is the editor the
     tool already generates configuration for.
  5. `odwg-010` **deny Odoo outside localhost**: `process.command` matches `odoo-bin`, so it covers workspaces,
     migration steps and the shell. Its action is `reject`. On WSL, `reject` behaves as `deny`, because the
     kernel lacks `CONFIG_INET_DIAG_DESTROY`: blocked the same, but the caller waits for its own timeout (60 s
     for SMTP). On a kernel that has it, `reject` fails fast.
  6. `odwg-020` **development infrastructure**, by destination host and for any process: GitHub (including
     `cli.github.com` and `*.githubusercontent.com`), PyPI, `*.astral.sh`, the Ubuntu archives and npm. Because
     Odoo matches `010` first, it can never use this rule.
- **Measured.** With these rules and `DefaultAction: deny`, the following work: `git fetch`, `gh`, `uv`, `pip`
  from a workspace venv, `apt-get update` (2 s) and a GitHub release download with `curl`. An unknown
  destination is blocked. `apt` needed `cli.github.com`, found because the prompt appeared during the spike.

### Operating the UI (documented, not automated)

- **Opening it.** From the Windows Start menu ("OpenSnitch (<distro>)"), or `opensnitch-ui &` in a WSL
  terminal. The daemon connects to it on `unix:///tmp/osui.sock`.
- **When it is open.** New connections prompt. With no answer, a prompt denies after 30 s. Prompts are shown
  one at a time: while one is open, other unruled connections wait, and their packets are dropped.
- **Scope of a new rule.** The prompt defaults to a rule on the process. "Deny `/usr/bin/curl` forever" blocks
  curl everywhere, which the spike did by accident. The docs show how to scope a rule to the destination
  instead, and how to delete a rule.
- **Event history.** It lives in memory by default (`[database] file=file::memory:`) and is lost when the UI
  closes. The docs show how to switch to a file with a retention limit.
- **Pausing.** `sudo systemctl stop opensnitch`, then `start` to resume.

### Mailpit

- **Install.** The upstream `mailpit-linux-amd64.tar.gz` of a pinned release, verified by the SHA-256 digest
  GitHub publishes for the asset. Mailpit publishes no checksum file and no attestation (checked). The binary
  goes to `/usr/local/bin/mailpit`.
- **Service.** A system unit `mailpit.service` runs as a dynamic user, with
  `--smtp 127.0.0.1:1025 --listen 127.0.0.1:8025`. From Windows, `http://localhost:8025` reaches it through
  WSL's localhost forwarding.
- **Generated `odoo.conf`.** Workspace and migration configs set `smtp_server = 127.0.0.1` and
  `smtp_port = 1025`. Measured: Odoo's mail went to Mailpit and was captured, addressed to the operator's test
  address, and nothing left.
- **The database overrides `odoo.conf`.** Measured: with a production-like `ir.mail_server` in the database,
  Odoo used it (`ir_mail_server.py`: a database server wins over `smtp_server`). OpenSnitch blocked it, but the
  mail was then neither sent nor visible.
- **Redirect action.** On a chosen database:
  - it points every `ir_mail_server` at `127.0.0.1:1025` with no encryption and clears its user and password;
  - it deactivates `fetchmail_server` if the table exists.
  
  Columns are touched only where they exist (`information_schema`), so it holds from 12 to 19. It needs
  `confirm_with_phrase`. The docs state it is for rehearsal copies only: a production cutover database keeps
  its servers.

### Live production migrations

The database that comes out goes back to production, so the redirect is never applied to it. OpenSnitch does
the protecting:
- the migration's `odoo-bin` steps are covered by `odwg-010`;
- the log records what was attempted, for review before cutover.

## Risks / Trade-offs

- **Default-deny blocks any tool without a rule until it is allowed.** → The baseline covers the
  development flow. The docs explain allowing a tool by destination from the UI, and pausing with
  `systemctl stop`.
- **Fail-closed.** A daemon crash blocks outbound traffic until restart. → The trade-off chosen for "deny in
  every case", with recovery documented. Acceptance kills the daemon to confirm.
- **`proc` costs more CPU than eBPF.** → Nothing was noticeable in the spike. It is the only method that held for
  long-running processes here.
- **`dest.host` rules depend on the daemon seeing the DNS answer.** A connection whose host it did not resolve
  falls to the default, which is deny, so it fails safe.
- **Pinned versions go stale.** → The support-matrix style: an update procedure, including signature
  re-verification, in `docs/egress-control.md`.
