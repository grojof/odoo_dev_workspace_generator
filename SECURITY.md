# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through
[GitHub Security Advisories for this repository](https://github.com/grojof/odoo_dev_workspace_generator/security/advisories/new)
— do not open a public issue. You will get an acknowledgement, and a fix or an assessment before any
public disclosure.

## Scope

This tool generates files and runs commands **on your own host, only after showing you the exact plan and
asking for confirmation** (destructive actions require typing an exact phrase). Security-relevant surfaces:

- **Shell and SQL built from operator input.**
  - Every value that reaches a command, a generated script or `odoo.conf` is validated by the checks in
    `odoo_dwg/models.py`: Odoo versions, the workspace name, database roles and names, OCA repository names,
    the database host and ports, and Python versions.
  - Profiles are validated whenever they are loaded, since a `workspace.json` may come from someone else.
  - Paths are quoted with `shlex.quote`.
  - Generated files are written through a heredoc whose delimiter never occurs in their content.
- **The generated `odoo.conf`.** Each instance binds to `http_interface = 127.0.0.1` and keeps Odoo's
  database-manager password at `admin_passwd = admin` — development defaults for a loopback-only instance.
  Change the password before exposing an instance on any other interface.
- **Root-run downloads.** `provision apply` downloads into `/var/cache/odoo_dwg`, a root-owned directory it
  creates with mode `700`, rather than a world-writable `/tmp`, so no other local user can swap an artifact
  between its checksum check and its install.
- **Downloaded artifacts.**
  - **wkhtmltopdf** is SHA-256-pinned.
  - **OpenSnitch** is SHA-512-pinned from the maintainer-signed checksum list, and
    `tools/verify_egress_pins.py` re-checks the signature and the signing key.
  - **Mailpit** is pinned to GitHub's recorded SHA-256.
  - Every install aborts on a mismatch.
- **Outbound firewall (OpenSnitch, opt-in).** It denies by default, fails closed if its daemon dies, and
  confines `odoo-bin` to localhost (plus DNS on port 53). It sorts ahead of every allow rule that could
  match a user process: only the loopback, DNS and `systemd-timesyncd` rules precede it, and none of those
  can match `odoo-bin`. It is a guard for development hosts, not a security boundary against a hostile local
  user: `root` can stop it.
- **Mail capture (Mailpit, opt-in).** It listens on `127.0.0.1` only. The mail redirect action rewrites a
  database's mail servers and asks for a confirmation phrase. It is meant for rehearsal copies only.
- The PostgreSQL loopback-trust configuration written by `provision apply` is a **development-only**
  convenience, documented as such; do not use it on shared or exposed hosts.

Supported versions: the latest `main`. There are no maintained release branches.
