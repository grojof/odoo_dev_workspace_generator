# Proposal

## Why

The OCA AEAT modules store each filed declaration's boxes in `l10n_es_aeat_tax_line`, linked to the journal
items that make them up. Each box points at the map line it was computed with, and that foreign key
cascades on delete. OCA dropped the 303 map of July 2021 to December 2022 from its 17.0 module, and one of
that map's boxes from its 13.0 module. At each of those module updates, Odoo deleted the records the module
no longer ships, and with them every box of the 2022 VAT returns. On the first client, all its 2022 returns
reached the target without a single box: the filed returns an auditor would open. Nothing failed.

## What Changes

- **At the source restore**, before its checkpoint, the driver copies into tables of its own every stored
  declaration box, its links to journal items, and the map lines and maps the boxes point at.
- **At the target**, after the post hook and before the grouped-items repair (so that repair moves the
  boxes' links too), it puts back whatever the chain deleted, with the same ids. Each column the target still
  has is cast to its type, and a text that became translatable goes in as its English value.
  - It checks that every box the source held is there with its number and filed amount, and keeps nothing
    otherwise.
  - It lists each box it put back in `logs/<target>-declaration-boxes-put-back.tsv` and drops its tables.
  - A link to a journal item the chain no longer has is counted, not put back.
- **A run from a source checkpoint without the kept declarations** records `filed-declarations-skipped` and
  says that only a run from the dump checks them.

Out of scope: computing a period again with a map the module no longer ships; the stored boxes are what was
filed.

## Capabilities

### Modified Capabilities

- `migration-run`: filed declarations are kept at the source restore and put back at the target.

## Impact

- New `odoo_dwg/declarations.py`; `odoo_dwg/templates.py`.
- `tests/test_declarations.py`, `tests/test_migration.py`.
- New `tools/verify_filed_declarations.py`; `tools/verify_migration_driver.py`.
- Docs: `docs/migration/running.md`, `CHANGELOG.md`, `docs/project/roadmap.md`, `CONTRIBUTING.md`, `AGENTS.md`.
- Validated on the first client's migrated database: the lost returns' boxes came back, with the same total
  of boxes as the source.
