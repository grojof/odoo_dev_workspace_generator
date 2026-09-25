# Proposal

## Why

A client module that is refactored while porting can be split: its data goes to one new module, and its
other parts to modules that are new. The first real case put an inventory numbering, a company invoice
and a BoM report in one Odoo 12 module, now three modules.

The client-modules stage could rename the old module into the part that owns its data, but it had no way
to install the other parts:
- `replaced` is a different fate: it uninstalls the old module;
- a `renamed` decision with more than one `to` was refused.

A module installed new also runs no migration scripts. So the operator had nowhere to say "and install
these", except by hand after the run.

## What Changes

- **A `renamed` decision may name several modules in `to`.** The first takes the old module: its record,
  its identifiers and its data, as a single rename does. The others are installed in the same Odoo run.
  `migrate modules` and the driver show it as a split.
- **Each module named is checked as before**: it must resolve in the target's sources, have a readable
  manifest of the target series, and be installable.
- **The split parts get nothing from the old module themselves.** Records that belong to them are handed
  over by the first module's own migration scripts, or rebuilt. The docs say so.
- `migrate decide … --decision renamed --to A B C` records it.

Out of scope: moving identifiers between modules automatically. Which record belongs to which part is
the ported code's knowledge, not the tool's.

## Capabilities

### Modified Capabilities

- `migration-preflight`: a `renamed` decision may name several modules; the first takes the old module,
  the rest are installed.

## Impact

- `odoo_dwg/carry.py`: renames take `to[0]`, and the rest join the installs. The `many-to` problem is
  gone.
- `odoo_dwg/i18n.py`, `tests/test_carry.py`, `tools/verify_migration_driver.py`.
- Docs: `docs/migration/running.md`, `docs/reference/commands.md`, `CHANGELOG.md`.
- Validated on the first client's migrated database: an Odoo 12 module split into three.
