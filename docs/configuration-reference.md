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

## Development versions and interpreters

First-class development targets are **17.0 / 18.0 / 19.0**, but a profile may name any version in the
[support matrix](support-matrix.md) (12.0–19.0), which is the single place the Python range, the recommended
interpreter and the PostgreSQL floor per version are declared — with the source behind each one.

Each instance's venv is built with an interpreter resolved against that matrix:

- The host `python3` is used whenever it is inside the version's declared range. On Ubuntu 24.04 that is
  3.12, which covers Odoo 15 through 19.
- When it is outside the range — an Odoo 14 instance on that same host, say, since 14 tops out at 3.10 —
  generation says so, naming the range, the detected version and the evidence tier of the bound, and offers
  to build that venv with a matching `uv`-provisioned interpreter (`uv venv --seed`, so the venv still has
  `pip`).
- The recommendation is a default, not a mandate: you can keep the host interpreter or name any other
  version. That is how a workspace reproduces a client's exact environment — pin the interpreter they run.

There is no profile field for the interpreter: it is asked at generation time, because the answer depends on
the host, not on the profile.

## Example

```json
{
  "name": "acme",
  "versions": ["17.0", "18.0"],
  "db_user": "acme",
  "oca_repos": ["web", "server-tools"]
}
```
