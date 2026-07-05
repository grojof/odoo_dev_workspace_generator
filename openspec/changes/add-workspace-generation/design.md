## Context

`odoo_dwg` F0 provides the layered skeleton (i18n/ui/prompts/system/models/cli) and a stubbed `workspace`
section. This change implements the workspace section by mirroring the sibling app `odoo_instance_manager`:
**pure `planners`** build `list[Command]`, **`system`** previews/applies them, and **`workflows/workspace.py`**
drives menus and discovery. The domain model already carries `WorkspaceConfig`/`InstanceConfig` with derived
names, ports, and Python floors; this change extends it (OCA repos, load/save) and adds `planners.py` +
`templates/`.

The layout being generated is the one validated in the prior generation and refined in the plan: a shared
read-only repo cache plus a per-client tree with per-instance venvs. Odoo facts (clone command, `addons_path`,
`odoo.conf` keys, per-version `requirements.txt`) are anchored to the official "Source install" and CLI/
`odoo.conf` reference pages.

## Goals / Non-Goals

**Goals:**
- Turn a validated JSON profile into a complete, ready-to-open workspace via previewed plans.
- Keep all file generation **pure** (rendered strings compared in tests) and all mutation in applied plans.
- Reuse a shared repo cache across workspaces; never re-clone or clobber existing resources.
- Emit English artifacts, including a per-workspace README that gives any assistant full context.

**Non-Goals:**
- Host provisioning (F2), OpenUpgrade migration (F3), AI/MCP emitters (F4).
- Running/validating a live Odoo or PostgreSQL — the real end-to-end launch is a WSL step, out of unit scope.
- Non-Odoo-Community editions; RTL/less toolchain wiring beyond what `provision` will later cover.

## Decisions

- **Pure `planners.py` returning `list[Command]`, mirroring the sibling.** File writes are emitted as
  `write_text_file_command(path, content, mode)` (heredoc + `chmod`), so tests assert on rendered content and
  the command list without shelling out. *Alternative:* write files directly in workflows — rejected; it
  breaks the plan→preview→apply contract and purity/testability.
- **Templates as Python string builders in `odoo_dwg/templates/`** (not a template engine) to stay
  stdlib-only. Token substitution via `str`/f-strings. *Alternative:* Jinja2 — rejected (runtime dependency).
- **Shared cache keyed by `<base>/.repos/odoo-<version>` and `<base>/.repos/oca/<repo>-<version>`**, cloned
  `--single-branch --branch <version>`. `addons-oca` in a workspace holds **symlinks** into that cache so many
  workspaces share one checkout. *Alternative:* per-workspace clones — rejected (disk + update cost).
- **venv per instance at `.venv/odoo<major>`**, built by an applied step running `python3 -m venv` +
  `pip install -r <shared repo>/requirements.txt`. Rendering never builds. The generated
  `scripts/setup_venv.sh` reproduces the same steps for the user. *Alternative:* one shared venv — rejected;
  versions pin incompatible dependencies.
- **Create-only vs manage-only split** enforced in `workflows/workspace.py`: generation refuses to overwrite
  existing custom addons/venvs/config and points to management; management discovers existing workspaces and
  gates destructive steps behind `confirm_with_phrase`. Mirrors the sibling's inviolable rule.
- **`odoo.conf` rendered version-adaptively** from `InstanceConfig` (e.g. `http_port` derived, `addons_path`
  composed custom→oca→`odoo/addons`), keeping keys traceable to the official CLI/`odoo.conf` reference.

## Risks / Trade-offs

- **Symlinks for `addons-oca`** → on filesystems without symlink support this degrades; mitigation: the target
  host is Linux (symlinks native), and the generator documents the assumption. Windows dev never creates them
  (generation is planned/tested, applied on WSL).
- **`pip install -r requirements.txt` can fail for a given host Python** → mitigation: dev versions (17–19)
  target Python ≥3.10 which is the documented floor; failures surface through the applied plan, not silently.
- **Shared cache staleness** (a branch moves) → mitigation: management "refresh repos" pulls; generation only
  clones when absent, never mutates a present clone implicitly.
- **Broad surface for one change** → mitigation: capabilities are split (configuration/generation/management)
  and tasks are ordered so configuration + rendering land and are tested before the applied clone/venv steps.

## Migration Plan

Additive only — no existing behavior changes. Land `models` extensions + `planners`/`templates` with unit
tests (pure), then wire `workflows/workspace.py` menus. The real clone→venv→`odoo-bin` launch is validated
manually on WSL Ubuntu 24.04 and recorded in `docs/`. Rollback is reverting the change; no persisted state.

## Open Questions

- Exact set of default OCA repositories to offer (leave configurable; ship an empty default).
- VSCode `launch.json` debug shape for Odoo (python debugger + `odoo-bin` args) — confirm against a real run
  on WSL before finalizing the template.
- Whether `setup_venv.sh` should prefer `uv` when present for speed (kept as a later enhancement; F1 uses
  `python3 -m venv` + `pip` to stay dependency-free).
