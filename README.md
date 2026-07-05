# odoo_dwg — Odoo development & migration workspace generator

A **zero-runtime-dependency** (Python standard library only) command-line tool that **generates and
maintains Odoo Community development workspaces** and **OpenUpgrade migration environments** on a **Linux
host** — WSL Ubuntu 24.04, a bare server, or a container. The host is *yours*; this tool prepares and manages
what runs on it. It is a sibling of [`odoo_instance_manager`](https://github.com/grojof/odoo_instance_manager_app)
and shares its UI, menus, and the safe **plan → preview → apply** contract.

> **Status: F1 + F2 done.** The **workspace** and **provision** sections are implemented and validated
> end-to-end on WSL Ubuntu 24.04; **migration** is next. See [`docs/roadmap.md`](docs/roadmap.md).

## Why not Docker?

The goal is a workspace as faithful as possible to production: a real Linux + PostgreSQL + venv-per-instance,
the way Odoo's own **"source install"** works. Docker (or WSL, or a plain server) is a fine *host* — but this
tool provisions and generates workspaces *on* whatever Linux you give it, rather than hiding it behind an image.

## What it does

Two optional user-facing **sections** plus one **mode**:

| Surface | What it does | Requires root? |
|---|---|---|
| **workspace** | Per-client workspaces: shared Odoo/OCA repo cache, per-instance venv, `addons-custom`/`addons-oca`, per-version `odoo.conf`, VSCode files, and a robust per-workspace README. | No (user's home) |
| **provision** *(optional)* | Prepare *a Linux host*: PostgreSQL + role, wkhtmltopdf, Node + rtlcss, per-version Python interpreters. Host-agnostic — never assumes WSL. | `apply` may |
| **migration** *(mode)* | OpenUpgrade chained upgrade **12 → 19** (sequential, no skips), per-version interpreters via `uv`, a checkpointing driver, optional Docker fallback for 12/13. | No |

Every host-mutating action shows the exact command **plan** and runs it only after you confirm.

## Requirements

- A **Linux** host (target: Ubuntu 24.04). Development *of this tool* works on any OS; real end-to-end
  generation is validated on WSL/Linux.
- `python3` ≥ 3.10 (the tool itself). Host tools it orchestrates — `git`, `psql`/`createdb`, and, for
  migration, `uv` (and optionally `docker`) — are checked by `provision check`, not bundled.

## Usage

```bash
python3 -m odoo_dwg            # interactive menu
python3 -m odoo_dwg workspace  # go straight to the workspace section
python3 -m odoo_dwg --help

ODWG_LANG=es python3 -m odoo_dwg   # Spanish UI (English is the default)
```

## Supported versions

- **Development:** Odoo **17.0 / 18.0 / 19.0** (first class).
- **Migration:** the full **12.0 → 19.0** OpenUpgrade chain (one step per version).
- **Python floors** (official "Source install"): 12→3.5, 13→3.6, 14→3.7, 17→3.10, 18→3.10.

## Design principles

Standard library only · English canonical (Spanish optional UI) · plan → preview → apply · pure planners ·
every Odoo/OpenUpgrade fact anchored to **official documentation** (see [`docs/`](docs/)) · assistant-agnostic
(no AI/MCP installed).

## Documentation & contributing

- [`docs/roadmap.md`](docs/roadmap.md) — phased plan (F0–F4).
- [`docs/workspace-layout.md`](docs/workspace-layout.md) — generated tree, conventions, WSL validation.
- [`docs/configuration-reference.md`](docs/configuration-reference.md) — the JSON profile fields.
- [`docs/provisioning.md`](docs/provisioning.md) — prepare a Debian/Ubuntu host (check / apply).
- [`CLAUDE.md`](CLAUDE.md) — guide for AI agents working on this project.
- Non-trivial changes are **spec-first** via OpenSpec (`/opsx:*`); specs live in `openspec/specs/`.

## License

AGPL-3.0-or-later.
