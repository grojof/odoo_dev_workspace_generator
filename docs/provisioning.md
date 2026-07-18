---
type: how-to
title: "Provisioning a Linux host"
description: "Use the provision section to make a Debian/Ubuntu host Odoo-ready."
audience: [developer]
updated: 2026-07-05
---

# Provisioning a Linux host

The optional **provision** section prepares a *Linux* host (bare server, WSL, or container) for Odoo
development. It is host-agnostic but **package-manager-specific**: this version targets the **Debian/Ubuntu
(apt) family**, detected from `/etc/os-release`. A non-apt host is reported and refused rather than guessed at.

```bash
python3 -m odoo_dwg provision      # menu: Check / Apply
```

## Check (read-only)

`Check host readiness` prints a capability table and changes nothing:

```
+-------+-------------------------+------------------------------------------+
| State | Capability              | Detail                                   |
+-------+-------------------------+------------------------------------------+
| OK    | Package family          | Debian/Ubuntu (apt) — noble              |
| OK    | Odoo build dependencies | all present                              |
| OK    | PostgreSQL              | installed and running                    |
| OK    | Dev role (odoo)         | present                                  |
| OK    | wkhtmltopdf             | wkhtmltopdf 0.12.6.1 (with patched qt)   |
| INFO  | Node.js (optional)      | not installed (only needed for RTL/less) |
+-------+-------------------------+------------------------------------------+
```

## Apply

`Apply` requires **root/sudo** and installs only what is missing, through plan → preview → confirm:

- **Odoo build dependencies** — the compiler toolchain and headers behind lxml, Pillow, psycopg2,
  python-ldap, etc. (validated against Odoo's source install).
- **PostgreSQL** — installed, enabled, and a `LOGIN CREATEDB` development role created idempotently. For a
  development host it also sets loopback (`127.0.0.1/::1`) to `trust` in `pg_hba.conf` so a workspace
  `odoo.conf` (which uses `db_host=127.0.0.1`) connects. **This is a dev-only convenience — not for
  production**; a password-auth mode is a planned follow-up.
- **wkhtmltopdf** — the Odoo-recommended patched build (0.12.6 for Odoo ≥ 15), downloaded for the host
  codename and **verified by SHA-256** before install; a mismatch aborts.
- **Node + rtlcss** *(opt-in)* — only needed for RTL/less asset compilation.
- **Docker Engine** *(opt-in)* — only needed for the Odoo 12/13 migration fallback steps. Installed as
  the distro-maintained **`docker.io`** package (no extra apt sources or GPG keys); if you prefer
  Docker's own `docker-ce` repository, follow the [official Docker docs](https://docs.docker.com/engine/install/)
  — the checks only care that a daemon responds. To use Docker as a non-root user, add yourself to the
  docker group (`usermod -aG docker <user>`, then re-login).
- **OpenUpgrade fallback images** *(opt-in)* — `docker pull odoo:13.0` / `odoo:12.0`, so the migration's
  Docker step cannot fail at run time on a missing image. The check table reports both image states.

## Official references

- Odoo source install (dependencies, PostgreSQL role): <https://www.odoo.com/documentation/18.0/administration/on_premise/source.html>
- wkhtmltopdf (which build to use): <https://github.com/odoo/odoo/wiki/Wkhtmltopdf>
- Supported versions / PostgreSQL: <https://www.odoo.com/documentation/18.0/administration/supported_versions.html>

## Acceptance (validated on WSL Ubuntu 24.04)

On the `OdooDevServerTest` distro (Ubuntu 24.04 noble, root, PostgreSQL 16): `provision apply` installed the
patched **wkhtmltopdf 0.12.6.1 (with patched qt)** (checksum verified), created the `odoo` role, and set
loopback trust; `provision check` then reported every capability OK. This matches, and automates, the manual
prerequisites that F1's end-to-end acceptance required.
