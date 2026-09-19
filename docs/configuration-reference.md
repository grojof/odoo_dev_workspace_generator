---
type: reference
title: "Workspace profile reference"
description: "The JSON profile fields that describe an odoo_dwg workspace."
audience: [developer]
updated: 2026-09-20
---

# Workspace profile reference

A workspace is described by a JSON profile (see `examples/workspace-acme.json`). Unknown keys are ignored so
older profiles keep loading; a former `addon_prefix` key, for example, is ignored. A profile is validated
**every time it is loaded**, when a workspace is created and whenever one is managed. The reason is that its
values end up in paths, generated scripts and `odoo.conf`, and a profile can come from anyone. A value that
fails is reported with its field, and nothing is planned.

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `name` | string | — (required) | Workspace/client id. Must match `^[a-z][a-z0-9_]{0,31}$` (filesystem- and PostgreSQL-safe). Reused for instance names and paths. |
| `versions` | string[] | `["18.0"]` | Odoo versions to host. At least one; each must be exactly one of the supported `"12.0"` … `"19.0"` (not `"18"`). Deduplicated and ordered by major. |
| `http_port_base` | int | `8069` | HTTP port of the lowest-major instance; higher majors get `+step` each. An integer from 1 to 64000. |
| `db_host` | string | `127.0.0.1` | PostgreSQL host written into each `odoo.conf`: a host name or an IP address. |
| `db_port` | int | `5432` | PostgreSQL port: an integer from 1 to 65535. |
| `db_user` | string | `odoo` | PostgreSQL role written into each `odoo.conf`: by default the shared development role that `provision apply` creates. Must match `^[a-z_][a-z0-9_]{0,62}$`. |
| `oca_repos` | string[] | `[]` | OCA repository names (e.g. `"web"`, `"server-tools"`), cloned per version from `github.com/OCA/<repo>` and symlinked into `addons-oca/odoo<major>/`. Letters, digits, `.`, `_` and `-`, never `..`. Empty by default — no opinionated preset. |

## Development versions and interpreters

A profile may name any version in the
[support matrix](support-matrix.md) (12.0–19.0), which is the single place the Python range, the recommended
interpreter and the PostgreSQL floor per version are declared — with the source behind each one.

Each instance's venv is built with an interpreter resolved against that matrix:

- The host `python3` is used whenever it is inside the version's declared range. On Ubuntu 24.04 that is
  3.12, which covers Odoo 15 through 19. Odoo 12 and 13 state no maximum, which is not evidence that a newer
  Python works (their pinned `gevent` does not build on 3.12), so for them the host is the default only up
  to the recommended 3.8.
- When it is outside the range — an Odoo 14 instance on that same host, say, since 14 tops out at 3.10 —
  generation says so, naming the range, the detected version and the evidence tier of the bound, and offers
  to build that venv with a matching `uv`-provisioned interpreter (`uv venv --seed`, so the venv still has
  `pip`).
- The recommendation is a default, not a mandate: you can keep the host interpreter or name any other
  version. That is how a workspace reproduces a client's exact environment — pin the interpreter they run.

There is no profile field for the interpreter: it is asked at generation time, because the answer depends on
the host, not on the profile.

## One development database role

Every workspace connects as `odoo`, the role `provision apply` creates by default and migration environments
use, so a freshly provisioned host serves a new workspace with no extra step. A role per workspace would add a
`sudo` step for each client and isolate nothing, since loopback authentication is `trust`
([`provisioning.md`](provisioning.md#why-trust-on-loopback)). Set `db_user` in the profile if you want another
role; `provision apply` creates whichever role you name.

The trade-off: Odoo's database selector lists the databases the connecting role owns, so every workspace's
selector shows every development database on the host — as it already does across the versions of one
workspace. Open the one you mean, or pass `-d <db>` to `odoo-bin`.

Existing workspaces keep their role: `workspace.json` records the resolved `db_user`, and managing a
workspace reads it from there.

## Example

```json
{
  "name": "acme",
  "versions": ["17.0", "18.0"],
  "oca_repos": ["web", "server-tools"]
}
```
