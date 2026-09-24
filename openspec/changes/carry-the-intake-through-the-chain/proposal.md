# Proposal

## Why

The first client's 12 → 18 rehearsal was prepared through the tool, and it stopped before migrating
anything. That was correct: the driver's coverage found a dependency no step could resolve. Getting there
exposed six gaps between the client intake and the chain:

1. **The chain's OCA repositories were chosen by hand**, from where modules came from at 12.0. The intake's
   availability check already knew that a core module moves into `bank-statement-import` at 14.0. It did
   not count a core module as *moved*, and nothing offered its table to the generation.
2. **Every menu action after generation forgot the OCA repositories** it linked, because they are recorded
   nowhere. The preflight then looked only in `addons/odoo<major>/oca` and reported every OCA module of the
   chain as missing.
3. **The menu's preflight and the driver disagreed.** The preflight read dependencies under a module's
   original name, so a module renamed at an earlier step was skipped. The driver stopped on it.
4. **A decision needed at one step was reported stale** at every step where the module has code.
5. **The chain's step configurations ignored the intake's `data_dir`**, so the steps would have looked for
   the client's attachments in Odoo's default location.
6. **The driver gave the working database no filestore.**

## What Changes

- Generation, after an intake, **proposes every OCA repository** the availability check finds a module in,
  at any step, together with those already linked. A core module found in an OCA repository later counts
  as moved.
- **Actions after generation read the linked repositories back** from each step's `oca` directory.
- **The preflight checks dependencies under the name each step knows** a module by, as the driver does.
- **A decision is stale only when no step of the chain needs it.**
- With an intake, **every step's configuration names the environment's `data_dir`**, and **the driver gives
  the working database a filestore** of hard links to the reference's, after every restore.

## Capabilities

### Modified Capabilities

- `migration-environment`: repositories proposed from the intake; `data_dir` and the filestore.
- `migration-preflight`: dependency names per step; stale decisions; repositories read back.

## Impact

- `odoo_dwg/intake.py`, `odoo_dwg/preflight.py`, `odoo_dwg/templates.py`, `odoo_dwg/workflows/migration.py`.
- Tests; `tools/verify_migration_driver.py` and `tools/verify_generated_shell.py` render the intake variant.
- Docs: `docs/migration.md`, `CHANGELOG.md`, `docs/roadmap.md`.
