## Why

The `workspace` section is the tool's core value: today it is a navigable stub. Odoo developers need a
reproducible, production-faithful per-client development workspace (a real Linux + PostgreSQL + venv-per-
version, the way Odoo's official "source install" works) without hand-wiring clones, venvs, ports, and
`odoo.conf` each time — and without the AI/MCP coupling that complicated the previous generation. This change
turns a JSON profile into a complete, ready-to-open workspace, generated as previewed plans.

## What Changes

- Introduce a JSON **workspace profile** (extending `WorkspaceConfig`) and the derived conventions it drives:
  instance name `odoo<major><name>`, per-version HTTP port (`base + step` per major), and a composed
  `addons_path` (custom + OCA + `odoo/addons`).
- Generate a **shared, read-only repo cache** under `<base>/.repos` with one
  `git clone --branch <ver> --single-branch` per configured Odoo version (odoo/odoo, plus optional OCA repos
  on the matching branch), reused across workspaces.
- Generate a **per-client workspace tree** `<base>/<name>/`: `addons-custom/`, `addons-oca/` (symlinks into
  the shared OCA cache), `config/odoo<major>.conf` per version, `.venv/odoo<major>` per instance, `scripts/`
  (`setup_venv.sh`, `run.sh`, shell helpers), a `<name>.code-workspace` + `.vscode/`
  (tasks/launch/settings/extensions), and a **robust per-workspace `README.md`** giving any human or AI full
  context (versions, paths, commands, how to run/debug).
- Enforce **create-only vs manage-only**: creation never mutates existing resources; management acts on an
  existing workspace with confirmation (regenerate a venv, refresh repos, add a version).
- Route every host-mutating step (clone, venv build, `pip install -r requirements.txt`) through the
  **plan → preview → apply** contract; generation of text files is pure and previewable.
- Add `odoo_dwg/planners.py` (pure builders returning `list[Command]`) and wire `workflows/workspace.py`;
  all generated artifacts are **English** text.

First-class development versions: **17.0 / 18.0 / 19.0**. Every `odoo.conf` key, the `addons_path` shape, and
the clone command are anchored to the official Odoo "Source install" and CLI/`odoo.conf` reference pages.

## Capabilities

### New Capabilities
- `workspace-configuration`: the JSON profile schema, its validation, and the deterministic conventions it
  derives (instance names, per-version ports, `addons_path`, filesystem layout).
- `workspace-generation`: create-only generation of the shared repo cache and the full per-client workspace
  tree (venvs, per-version `odoo.conf`, VSCode files, per-workspace README), via plan → preview → apply.
- `workspace-management`: manage-only operations on an existing workspace (regenerate/repair a venv, refresh
  the shared repos, add an Odoo version) that mutate existing resources only after confirmation.

### Modified Capabilities
<!-- None: this is the first behavior in the project; no existing spec changes. -->

## Impact

- **Code**: new `odoo_dwg/planners.py`; `odoo_dwg/models.py` (profile fields, load/save, OCA repo entries);
  `odoo_dwg/workflows/workspace.py` (menus, plan assembly, discovery); new `odoo_dwg/templates/` text
  (odoo.conf, VSCode JSON, README, bash scripts). `system.py` gains only generic probes if needed.
- **Host tools orchestrated** (not Python deps, checked before use): `git`, `python3 -m venv`, `pip`.
- **Tests**: unit tests assert rendered template text and config derivation with `tmp_path`, no shelling out
  and no live Odoo/PostgreSQL.
- **Docs**: new `docs/` pages (workspace layout, configuration reference) and README map update.
- **Not verifiable on Windows**: the real clone → venv → `odoo-bin` launch is validated on WSL Ubuntu 24.04;
  the change ships with that end-to-end step called out as host-dependent.
- **Out of scope** (later phases): provisioning (F2), OpenUpgrade migration (F3), AI/MCP emitters (F4).
