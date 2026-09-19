---
type: reference
title: "Workspace layout"
description: "The directory structure odoo_dwg generates for a client workspace and the shared repo cache."
audience: [developer]
updated: 2026-09-19
---

# Workspace layout

`odoo_dwg` generates two things under the base directory (`~/odoo-workspaces` by default): a **shared,
read-only repo cache** reused across workspaces, and one **per-client workspace** tree.

```
~/odoo-workspaces/
├── .repos/                              # shared cache (one clone per version)
│   ├── odoo-17.0/  odoo-18.0/  ...      # git clone --branch <ver> --single-branch
│   └── oca/<repo>-<ver>/ ...            # OCA repos on the matching branch
└── <name>/                             # a client workspace
    ├── addons-custom/                   # your modules
    ├── addons-oca/odoo<major>/<repo>    # per-version symlinks into .repos/oca
    ├── config/odoo<major>.conf          # one config per version
    ├── .venv/odoo<major>/               # one virtualenv per version
    ├── scripts/setup_venv.sh            # (re)build every venv + install requirements
    ├── scripts/run-odoo<major>.sh       # launch one instance
    ├── .vscode/                         # tasks / launch / settings / extensions
    ├── <name>.code-workspace
    ├── odools.toml                      # official Odoo language server profiles (Odoo >= 14)
    ├── workspace.json                   # saved profile (used by the manage flow)
    └── README.md                        # full context for humans and AI assistants
```

## Conventions

- **Instance name**: `odoo<major><name>` (e.g. `odoo18acme`).
- **Per-version HTTP port**: `http_port_base + step` per major, ordered by major, so versions never collide
  (e.g. base 8069 → 8069 / 8079 / 8089). The live-chat/bus port is `http_port + 1000`.
- **Composed `addons_path`** (precedence): `addons-custom` → each OCA repo (via its per-version symlink) →
  the shared `odoo/addons`.

The clone command, `addons_path`, and `odoo.conf` keys follow the official Odoo documentation:

- Source install: <https://www.odoo.com/documentation/18.0/administration/on_premise/source.html>
- CLI / `odoo.conf` reference: <https://www.odoo.com/documentation/18.0/developer/reference/cli.html>

## End-to-end validation (WSL Ubuntu 24.04 only)

Generating the files is verified by unit tests on any OS. Actually **building and launching** a workspace is
intrinsically Linux and is validated by hand on WSL Ubuntu 24.04:

```bash
# On the Linux host, after generating the workspace:
cd ~/odoo-workspaces/<name>
bash scripts/setup_venv.sh                      # python3 -m venv + pip install -r requirements.txt
createdb <name>                                 # PostgreSQL role/db must exist (see provision, F2)
bash scripts/run-odoo18.sh                       # odoo-bin -c config/odoo18.conf → serves on its port
```

This step is host-dependent and is **not** run in CI; it is the manual acceptance check for the change.

## Editor

The workspace is set up for the **official** Odoo extension (`Odoo.odoo`) and its language server: an
`odools.toml` with one profile per version (switch it from the status bar), Pylance turned off so Python is
analysed once, and no `jsconfig.json`. What is emitted, what is deliberately not, and how to keep up with the
extension's releases: [`editor-integration.md`](editor-integration.md).
