---
type: how-to
title: "Provisioning a Linux host"
description: "Use the provision section to make a supported Ubuntu host Odoo-ready."
audience: [developer]
updated: 2026-09-20
---

# Provisioning a Linux host

The optional **provision** section prepares a *Linux* host (bare server, WSL, or container) for Odoo
development. The host releases it supports are declared in the
[support matrix](support-matrix.md) — **Ubuntu 24.04** — detected from `/etc/os-release`. Any other
host is reported by `check` and refused by `apply` rather than guessed at: earlier versions accepted the whole
apt family, which implied Debian support that was never validated.

```bash
python3 -m odoo_dwg provision      # menu: Check / Apply / Outbound firewall and mail capture
```

## Check (read-only)

`Check host readiness` prints a capability table, changes nothing and **never asks for a password**. PostgreSQL's
state and version come from `pg_lsclusters`. The development role is checked by logging in as it over loopback,
or through `sudo -n`. When neither works, the role row says it could not be checked (WARN), instead of claiming
it is missing. The loopback-auth row asks **PostgreSQL itself** (`pg_hba_file_rules`, which needs `sudo`)
rather than parsing `pg_hba.conf`, so it sees the rules the server actually uses — continuations folded,
`include` files resolved — and warns when every role, `postgres` included, may connect over TCP without a
password:

```
+-------+-----------------------------------------+------------------------------------------------+
| State | Capability                              | Detail                                         |
+-------+-----------------------------------------+------------------------------------------------+
| OK    | Host release                            | Ubuntu 24.04 LTS (noble)                       |
| OK    | Odoo build dependencies                 | all present                                    |
| OK    | PostgreSQL                              | installed and running                          |
| OK    | PostgreSQL version                      | 16 (Odoo 19.0 requires 13.0)                   |
| OK    | Dev role (odoo)                         | present                                        |
| OK    | PostgreSQL loopback auth                | trust for odoo only                            |
| OK    | wkhtmltopdf                             | wkhtmltopdf 0.12.6.1 (with patched qt)         |
| OK    | Node.js (optional)                      | present                                        |
| INFO  | rtlcss (optional)                       | not installed (only for right-to-left          |
|       |                                         | languages)                                     |
| OK    | uv (interpreters)                       | present — provides 3.8, 3.9, 3.10 …            |
| INFO  | Host python3                            | 3.12                                           |
| INFO  | Egress firewall — OpenSnitch (optional) | not installed                                  |
| INFO  | Mail capture — Mailpit (optional)       | not installed                                  |
+-------+-----------------------------------------+------------------------------------------------+
```

## Apply

`Apply` requires **root/sudo** and installs only what is missing, through plan → preview → confirm:

- **Odoo build dependencies** — the compiler toolchain and headers behind lxml, Pillow, psycopg2,
  python-ldap, etc. (validated against Odoo's source install).
- **PostgreSQL** — installed, enabled, and a `LOGIN CREATEDB` development role created idempotently. For a
  development host it also sets loopback (`127.0.0.1/::1`) to `trust` in `pg_hba.conf` **for that role
  only** — never for `all` — so a workspace `odoo.conf` (which uses `db_host=127.0.0.1`) connects while a
  local user still cannot become `postgres`. A blanket loopback `trust` this tool wrote before is put back
  to `scram-sha-256`. **This is a dev-only convenience — not for
  production** (see below). The role defaults to `odoo`, the one workspaces and migration environments
  connect as; a role name must be a plain PostgreSQL identifier (`^[a-z_][a-z0-9_]{0,62}$`) or apply stops
  before planning.
  The `pg_hba.conf` step runs on an already-provisioned host too, so a host left with a blanket loopback
  `trust` by an earlier version is narrowed the next time you apply; when the rules are already in that
  shape, nothing is planned. What counts as a blanket `trust` is decided by the **method, not the address**,
  on **every connection type** (`host`, `hostssl`, `hostnossl`, `hostgssenc`, `hostnogssenc`): any rule for
  every role whose method is `trust` — `127.0.0.1/32`, `localhost`, `samehost`,
  `127.0.0.1 255.255.255.255`, and equally `all`, `0.0.0.0/0` or `127.0.0.0/8`, which contain loopback
  without naming it. `hostssl` matters in particular: Ubuntu 24.04 ships `ssl = on` and clients prefer TLS,
  so a `hostssl` rule is the one your loopback connection is matched against.

  The role's own line is inserted **before the first `host` rule of any kind**, because `pg_hba` is
  first-match-wins: a line below a rule that already matches the connection is never read, and a line that
  is merely *present* is not a narrowing. The step ends by **connecting as the role over loopback**: if it
  cannot, apply stops there instead of reporting a narrowing that does not work.

  After reloading, apply **asks the server what rules it now has** and fails the step, naming the file and
  line — which may be one the rewriter never saw — when any of these is true:

  1. PostgreSQL reports a rule it could not parse. It then refused to load the file and is **still running
     the previous rules**, while the file on disk reads as narrowed. `pg_ctl reload` reports success either
     way, so nothing else would notice.
  2. A rule still trusts every role over TCP — unless that rule's own line quotes its fields, since `"all"`
     in quotes is a role literally named `all` and not the keyword.
  3. A `trust` rule names its roles by pattern (`/…`) or group (`+…`), which apply cannot rule out: narrow
     that rule by hand.
  4. The first rule PostgreSQL matches for your role is not the plain `host` trust rule it just added.

  Only then does it connect as the role. Every defect this feature has had was a step reporting a success
  that had not happened, so success is now something PostgreSQL confirms.

  The **rewriter** still reads text, and refuses rather than rewrite a file whose rules it cannot read one
  line at a time — an `include` directive, or a record continued with a trailing backslash. It says which of
  the two it found: narrow that file by hand, or join the continued lines, then run apply again.

  The check says **unknown** (WARN) instead of claiming either answer — and apply plans the narrowing rather
  than assuming it is done — when PostgreSQL is stopped, when the view cannot be read without `sudo`, when
  the server reports a rule it could not parse, or when a `trust` rule names its roles by pattern (`/…`) or
  group (`+…`), which cannot be told to cover every role.

  Apply also acts when a probe could not answer: PostgreSQL installed but stopped, a role it could not check
  without a password, a rule set it could not read. Everything it plans is idempotent, so the worst case is a
  no-op, while the alternative was telling you the host was ready when it had no role at all.
- **wkhtmltopdf** — the Odoo-recommended patched build (0.12.6 for Odoo ≥ 15), downloaded for the host
  codename and **verified by SHA-256** before install; a mismatch aborts. 0.12.5, which Odoo recommends up to
  14, is not provisioned. When no verified build is pinned for the host, `apply` says so instead of skipping
  it silently.
- **rtlcss, with Node.js** *(opt-in)*: only needed if users work in a right-to-left language (Arabic, Hebrew,
  Persian…).
  - **What it does:** Odoo runs `rtlcss` only to mirror its CSS for those languages
    (`base/models/assetsbundle.py`). Without it, Odoo logs a warning and serves the stylesheet unmirrored.
  - **Not needed for:** styles themselves, which since Odoo 12 are SCSS compiled in Python.
  - **How it is installed:** without recommended packages. With them, `apt` pulled in 455 packages, a GUI
    terminal among them.
  - **If Node already comes from nvm,** `npm install -g rtlcss` is enough.
- **Outbound firewall — OpenSnitch** *(opt-in)*: denies every outbound connection without a rule, asks in its
  window when that is open, and logs every decision. Odoo may reach only localhost, plus DNS on port 53,
  while the development tools keep their hosts. The package is pinned and verified, the configuration hardened, and the baseline
  rules installed. See [egress-control](egress-control.md).
- **Mail capture — Mailpit** *(opt-in)*: a local SMTP server (`127.0.0.1:1025`) with a web UI (`:8025`). Every
  generated `odoo.conf` sends mail there, so it is read and never delivered. See
  [egress-control](egress-control.md#mail-capture).

## Why `trust` on loopback

`provision apply` lets the development role connect from `127.0.0.1` / `::1` without a password. That is a
deliberate choice for a local development box — nothing to generate, store or leak — and it is why the generated
`odoo.conf` carries no `db_password`. It is **not** a setup for a shared or remote PostgreSQL. If you need
password authentication, do it by hand: `ALTER ROLE odoo WITH PASSWORD '...'`, change those two `pg_hba.conf`
lines from `trust` to `scram-sha-256`, reload PostgreSQL, and add `db_password` to each `config/odoo<major>.conf`
yourself.

## Official references

- Odoo source install (dependencies, PostgreSQL role): <https://www.odoo.com/documentation/18.0/administration/on_premise/source.html>
- wkhtmltopdf (which build to use): <https://github.com/odoo/odoo/wiki/Wkhtmltopdf>
- Supported versions / PostgreSQL: <https://www.odoo.com/documentation/18.0/administration/supported_versions.html>

## Acceptance (validated on WSL Ubuntu 24.04)

On the `OdooDevServerTest` distro (Ubuntu 24.04 noble, root, PostgreSQL 16): `provision apply` installed the
patched **wkhtmltopdf 0.12.6.1 (with patched qt)** (checksum verified), created the `odoo` role, and set
loopback trust; `provision check` then reported every capability OK. This matches, and automates, the manual
prerequisites that F1's end-to-end acceptance required.
