---
type: reference
title: "Workspace profile reference"
description: "The JSON profile fields that describe an odoo_dwg workspace."
audience: [developer]
updated: 2026-07-05
---

# Workspace profile reference

A workspace is described by a JSON profile (see `examples/workspace-acme.json`). Unknown keys are ignored so
older profiles keep loading. Loading a profile validates it before use.

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `name` | string | — (required) | Workspace/client id. Must match `^[a-z][a-z0-9_]{0,31}$` (filesystem- and PostgreSQL-safe). Reused for instance names, `db_user`, and `addon_prefix`. |
| `versions` | string[] | `["18.0"]` | Odoo versions to host (e.g. `"18.0"`). At least one; each must be a parseable Odoo version. Deduplicated and ordered by major. |
| `addon_prefix` | string | = `name` | Prefix for scaffolded custom modules. |
| `http_port_base` | int | `8069` | HTTP port of the lowest-major instance; higher majors get `+step` each. |
| `db_host` | string | `127.0.0.1` | PostgreSQL host written into each `odoo.conf`. |
| `db_port` | int | `5432` | PostgreSQL port. |
| `db_user` | string | = `name` | PostgreSQL role written into each `odoo.conf`. |
| `oca_repos` | string[] | `[]` | OCA repository names (e.g. `"web"`, `"server-tools"`), cloned per version from `github.com/OCA/<repo>` and symlinked into `addons-oca/odoo<major>/`. Empty by default — no opinionated preset. |

## Development versions and Python floors

First-class development targets are **17.0 / 18.0 / 19.0**. The documented minimum Python per Odoo major
(official "Source install"): 12→3.5, 13→3.6, 14→3.7, 17→3.10, 18→3.10. On Ubuntu 24.04 the system Python is
3.12, which covers 17–19.

- Source install: <https://www.odoo.com/documentation/18.0/administration/on_premise/source.html>
- Supported versions / PostgreSQL: <https://www.odoo.com/documentation/18.0/administration/supported_versions.html>

## Example

```json
{
  "name": "acme",
  "versions": ["17.0", "18.0"],
  "db_user": "acme",
  "oca_repos": ["web", "server-tools"]
}
```
