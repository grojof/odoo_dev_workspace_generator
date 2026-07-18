# Proposal — add-migration-preflight

## Why

A real migration today can fail minutes or hours in, for reasons that were all detectable before
starting: Docker missing for the 12/13 step (the flow only prints a text warning), images not pulled,
PostgreSQL unreachable, a dump that does not restore, a declared source version that does not match the
database, or installed OCA/custom modules whose per-version addons are simply not present anywhere in the
migration environment (it currently has **no defined place** for non-core addons). Failing early with a
clear, reusable verification saves whole test cycles.

## What Changes

- **Provision knows about the migration toolchain.** `provision check` gains rows for `uv`, `docker`
  (binary present *and* daemon responding), and — informational — the OpenUpgrade fallback images.
  `provision apply` gains two opt-in plans: install Docker Engine (apt) and pull the fallback images
  (`odoo:13.0` / `odoo:12.0`).
- **New "Preflight check" action in the migration menu.** Read-only verification report (same table UX as
  `provision check`) over: host tools required by the chain (uv; docker + daemon + images only when the
  chain needs them), PostgreSQL reachability and role, the source dump (exists, readable,
  `pg_restore --list` parses), the database's actual Odoo version (from `ir_module_module`) vs. the
  declared source, the installed-module list classified core / OCA / custom, and per-version addons
  presence in the environment's addons layout.
- **The migration environment gets an addons layout.** Per target version: `addons/<major>/custom` and
  `addons/<major>/oca`, threaded into each step's `addons_path`/conf, with the generated README/docs
  explaining what to place there (the migrated branch of each module).
- **The same preflight runs automatically** at the start of `Generate a migration environment` (host-level
  subset) and inside `run_migration.sh` before touching the database (full set) — one implementation,
  called from menu and flows alike, mirroring how provision probes are reused.
- **Operator guide** in `docs/migration.md`: how to point at the source dump/DB, where to place custom and
  OCA addons, the preflight procedure, and what each failure means.

Out of scope: migrating custom module *code* between versions (oca-port / odoo-module-migrator remain the
referenced tools); automatic fixing of preflight failures beyond offering the existing provision plans;
any non-apt host.

## Capabilities

### New Capabilities

- `migration-preflight`: the verification capability — host-tool checks scoped to the chain, PostgreSQL
  checks, dump integrity, DB-version match, module classification, addons-presence — exposed as a menu
  action and reused by the generate flow and the run driver.

### Modified Capabilities

- `provision-check`: readiness table gains `uv` and `docker` (binary + daemon) rows and fallback-image
  status.
- `provision-apply`: two new opt-in plans — Docker Engine install and OpenUpgrade fallback image pulls.
- `migration-environment`: defines the per-version custom/OCA addons layout and threads it into each
  step's config; generation runs the host-level preflight subset first.
- `migration-run`: the driver runs the full preflight before restoring/migrating and aborts on failures.

## Impact

- `odoo_dwg/system.py` — new probes (docker daemon, image presence, `pg_restore --list`, psql scalar
  query helper).
- `odoo_dwg/provisioning.py` — new fact fields + rows.
- `odoo_dwg/planners.py` — Docker Engine install plan, image-pull plan, addons-layout directories in the
  migration tree.
- `odoo_dwg/templates.py` — per-step conf `addons_path` gains the addons layout; `run_migration.sh` gains
  a preflight section; migration README/docs text.
- `odoo_dwg/workflows/migration.py` (+ `provision.py`) — new menu action, auto-invocation, i18n strings.
- `openspec/specs/` — one new spec, four delta specs. Tests for every pure piece.
- Not verifiable from Windows (needs the WSL host): Docker Engine apt install shape, whether
  `odoo:12.0`/`odoo:13.0` still pull (Hub returned HTTP 200 in F3, tags are delisted), `pg_restore --list`
  behavior on old-version dumps, and reading `ir_module_module` — which requires a restored database, a
  design decision for design.md (query the restored working DB vs. a temporary restore).
