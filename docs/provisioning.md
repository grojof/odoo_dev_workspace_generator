---
type: how-to
title: "Provisioning a Linux host"
description: "Use the provision section to make a supported Ubuntu host Odoo-ready."
audience: [developer]
updated: 2026-09-17
---

# Provisioning a Linux host

The optional **provision** section prepares a *Linux* host (bare server, WSL, or container) for Odoo
development. The host releases it supports are declared in the
[support matrix](support-matrix.md) — **Ubuntu 24.04** — detected from `/etc/os-release`. Any other
host is reported by `check` and refused by `apply` rather than guessed at: earlier versions accepted the whole
apt family, which implied Debian support that was never validated.

```bash
python3 -m odoo_dwg provision      # menu: Check / Apply
```

## Check (read-only)

`Check host readiness` prints a capability table and changes nothing:

```
+-------+-------------------------+------------------------------------------+
| State | Capability              | Detail                                   |
+-------+-------------------------+------------------------------------------+
| OK    | Host release            | Ubuntu 24.04 LTS (noble)                 |
| OK    | Odoo build dependencies | all present                              |
| OK    | PostgreSQL              | installed and running                    |
| OK    | Dev role (odoo)         | present                                  |
| OK    | wkhtmltopdf             | wkhtmltopdf 0.12.6.1 (with patched qt)   |
| OK    | PostgreSQL version      | 16 (Odoo 19.0 requires 13.0)             |
| INFO  | Node.js (optional)      | not installed (only needed for RTL/less) |
| OK    | uv (interpreters)       | present — provides 3.8, 3.10, 3.12 …     |
| INFO  | Host python3            | 3.12                                     |
+-------+-------------------------+------------------------------------------+
```

## Apply

`Apply` requires **root/sudo** and installs only what is missing, through plan → preview → confirm:

- **Odoo build dependencies** — the compiler toolchain and headers behind lxml, Pillow, psycopg2,
  python-ldap, etc. (validated against Odoo's source install).
- **PostgreSQL** — installed, enabled, and a `LOGIN CREATEDB` development role created idempotently. For a
  development host it also sets loopback (`127.0.0.1/::1`) to `trust` in `pg_hba.conf` so a workspace
  `odoo.conf` (which uses `db_host=127.0.0.1`) connects. **This is a dev-only convenience — not for
  production** (see below). The role defaults to `odoo`, the one workspaces and migration environments
  connect as; a role name must be a plain PostgreSQL identifier (`^[a-z_][a-z0-9_]{0,62}$`) or apply stops
  before planning.
- **wkhtmltopdf** — the Odoo-recommended patched build (0.12.6 for Odoo ≥ 15), downloaded for the host
  codename and **verified by SHA-256** before install; a mismatch aborts.
- **Node + rtlcss** *(opt-in)* — only needed for RTL/less asset compilation.
- **Outbound firewall — OpenSnitch** *(opt-in)*: denies every outbound connection without a rule, asks in its
  window when that is open, and logs every decision. Odoo may reach only localhost, while the development
  tools keep their hosts. The package is pinned and verified, the configuration hardened, and the baseline
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
