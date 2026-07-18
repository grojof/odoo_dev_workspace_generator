# odoo_dwg — Odoo development & migration workspace generator

A **zero-runtime-dependency** (Python standard library only) command-line tool that **generates and
maintains Odoo Community development workspaces** and **OpenUpgrade migration environments** on a **Linux
host** — WSL Ubuntu 24.04, a bare server, or a container. The host is *yours*; this tool prepares and manages
what runs on it. It is a sibling of [`odoo_instance_manager`](https://github.com/grojof/odoo_instance_manager_app)
and shares its UI, menus, and the safe **plan → preview → apply** contract.

> **Status:** all three surfaces — **workspace**, **provision**, and **migration** (now with preflight
> verification and custom-module staging) — are implemented and validated on WSL Ubuntu 24.04.
> See [`docs/roadmap.md`](docs/roadmap.md).

## How it works

Nothing touches your host without you seeing exactly what will run:

```mermaid
flowchart LR
    OP([Operator]) --> CLI[odoo-dwg menu / CLI]
    CLI --> W[workspace]
    CLI --> P[provision]
    CLI --> M[migration]
    W & P & M --> PLAN[Command plan]
    PLAN --> PREVIEW[Preview every command]
    PREVIEW --> CONFIRM{Confirm?\ndestructive → exact phrase}
    CONFIRM -- yes --> APPLY[Apply on the Linux host]
    CONFIRM -- no --> CLI
    APPLY --> OUT[(Workspaces · Host packages ·\nMigration environments)]
```

## Why not Docker?

The goal is a workspace as faithful as possible to production: a real Linux + PostgreSQL + venv-per-instance,
the way Odoo's own **"source install"** works. Docker (or WSL, or a plain server) is a fine *host* — but this
tool provisions and generates workspaces *on* whatever Linux you give it, rather than hiding it behind an image.

## What it does

Two optional user-facing **sections** plus one **mode**:

| Surface | What it does | Requires root? |
|---|---|---|
| **workspace** | Per-client workspaces: shared Odoo/OCA repo cache, per-instance venv, `addons-custom`/`addons-oca`, per-version `odoo.conf`, VSCode files, and a robust per-workspace README. | No (user's home) |
| **provision** *(optional)* | Prepare *a Linux host*: PostgreSQL + role, wkhtmltopdf, Node + rtlcss, and the migration toolchain (uv, Docker Engine + OpenUpgrade images, both opt-in). Host-agnostic — never assumes WSL. | `apply` may |
| **migration** *(mode)* | OpenUpgrade chained upgrade **12 → 19** (sequential, no skips): **preflight verification** (host, dump, database, addons coverage), per-version interpreters via `uv`, **custom-module staging** (OCA `odoo-module-migrator` + analysis findings + scaffolds), a checkpointing driver, and environment cleanup. | No |

## Install & first run

```bash
git clone https://github.com/grojof/odoo_dev_workspace_generator
cd odoo_dev_workspace_generator

python3 -m odoo_dwg                 # interactive menu (asks language on start)
```

Common invocations:

```bash
python3 -m odoo_dwg workspace       # create/manage per-client workspaces
python3 -m odoo_dwg provision       # check first — read-only readiness table:
#   State  Capability               Detail
#   OK     PostgreSQL               installed and running
#   OK     wkhtmltopdf              wkhtmltopdf 0.12.6.1 (with patched qt)
#   OK     uv (migration)           present
#   WARN   Docker daemon            not responding (service down or missing docker-group permission)

python3 -m odoo_dwg migrate         # generate env / preflight / stage custom modules / clean
ODWG_LANG=es python3 -m odoo_dwg    # Spanish UI (English is the default)
```

Every command, menu action, and confirmation phrase: [`docs/commands.md`](docs/commands.md).

## Requirements

- A **Linux** host (target: Ubuntu 24.04). Development *of this tool* works on any OS; real end-to-end
  generation is validated on WSL/Linux.
- `python3` ≥ 3.10 (the tool itself). Host tools it orchestrates — `git`, `psql`/`createdb`, and, for
  migration, `uv` (and optionally `docker`) — are checked by `provision check`, not bundled.

## Supported versions

- **Development:** Odoo **17.0 / 18.0 / 19.0** (first class).
- **Migration:** the full **12.0 → 19.0** OpenUpgrade chain (one step per version).
- **Python floors** (official "Source install"): 12→3.5, 13→3.6, 14→3.7, 17→3.10, 18→3.10.

## Design principles

Standard library only · English canonical (Spanish optional UI) · plan → preview → apply · pure planners ·
every Odoo/OpenUpgrade fact anchored to **official documentation** (see [`docs/`](docs/)) · assistant-agnostic
(no AI/MCP installed).

## Documentation

By surface:

- **Using the tool** — [`docs/commands.md`](docs/commands.md) (every command and menu action).
- **Workspaces** — [`docs/workspace-layout.md`](docs/workspace-layout.md) (generated tree, conventions) ·
  [`docs/configuration-reference.md`](docs/configuration-reference.md) (JSON profile fields).
- **Provisioning** — [`docs/provisioning.md`](docs/provisioning.md) (Debian/Ubuntu check/apply, Docker option).
- **Migration** — [`docs/migration.md`](docs/migration.md) (interpreters, preflight, staging, checkpointing driver).
- **Project** — [`docs/roadmap.md`](docs/roadmap.md) (phases + backlog) · [`CLAUDE.md`](CLAUDE.md) (AI-agent
  guide) · [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`SECURITY.md`](SECURITY.md) ·
  [`CHANGELOG.md`](CHANGELOG.md).
- Non-trivial changes are **spec-first** via OpenSpec (`/opsx:*`); specs live in `openspec/specs/`.

## License

AGPL-3.0-or-later.
