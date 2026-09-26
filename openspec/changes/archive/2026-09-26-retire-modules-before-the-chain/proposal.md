# Proposal

## Why

Some modules installed in the source have no code at a later step of the chain: Odoo dropped them, OCA never
ported them to one version, or they are unused leftovers. The intake rehearses uninstalling them on a
throwaway clone and names every difference it made. But the real uninstall, on the copy that enters the
chain, is not part of the chain: on the first client it was applied by hand to a prepared source, so a run
from a fresh dump of production would not do it, and nothing would check that the real uninstall removed
only what the rehearsal said.

A migration has to be repeatable on any copy, on the day of the cutover, with no hand work.

## What Changes

- **A decision can retire a module before the chain.** A `dropped` decision takes `"when": "before-chain"`
  (`migrate decide MODULE --decision dropped --before-chain`). Without it, `dropped` keeps its meaning: the
  client-modules stage uninstalls the module at the target.
- **What an uninstall may remove is decided up front.** The decisions file holds an `accepted_losses`
  list: table or `table.column`, with the reason (`migrate accept-loss TABLE[.COLUMN] --reason …`). These are
  the losses the rehearsal named that the operator accepts, for example a setting of the retired feature.
- **The driver retires them right after restoring the source dump**, before the source's journal-item taxes
  and declarations are kept, and before the source checkpoint:
  - it refuses to start when an installed module depends on one of them and is not retired as well;
  - it uninstalls them with the source version's own Odoo, as the Apps screen does, and checks they are gone;
  - it compares every table's row count and every column before and after. A table that lost rows, or a
    column that disappeared with values, is **data**, unless it is Odoo's metadata (models, fields, views,
    menus, actions, access rules, translations), a transient model's table, or an accepted loss;
  - any data lost that is not accepted stops the run before the source checkpoint, naming it;
  - every difference goes to `logs/00_source-retired.tsv`, with its kind and, for an accepted loss, its reason.
- **Coverage** already counts a `dropped` module as decided; nothing changes there.

Out of scope: choosing which modules to retire (the intake's coverage and rehearsal answer that), and
uninstalling at other steps.

## Capabilities

### Modified Capabilities

- `migration-run`: modules decided `dropped` before the chain are uninstalled after the source restore, with
  a data guard.
- `migration-preflight`: a `dropped` decision may say `before-chain`, and the decisions file may accept named
  losses.

## Impact

- `odoo_dwg/carry.py` (the decision's field and the list of modules to retire), new `odoo_dwg/retire.py`
  (the snapshot and comparison SQL), `odoo_dwg/templates.py` (the stage), `odoo_dwg/workflows/decide.py`
  and `odoo_dwg/cli.py` (`--before-chain`, `accept-loss`), `odoo_dwg/i18n.py`.
- Tests: `tests/test_carry.py`, `tests/test_retire.py`, `tests/test_migration.py`, `tests/test_cli.py`.
- New `tools/verify_retired_modules.py` (the comparison against a throwaway PostgreSQL);
  `tools/verify_migration_driver.py` (the stage, with a stub source Odoo).
- Docs: `docs/migration/running.md`, `docs/reference/commands.md`, `CHANGELOG.md`, `docs/project/roadmap.md`,
  `CONTRIBUTING.md`, `AGENTS.md`.
- Validated on the first client: a run from its original copy retires the same modules the prepared source
  lacks, loses only the accepted items, and the rest of the chain gives the same result.
