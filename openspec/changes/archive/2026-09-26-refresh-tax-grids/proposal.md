# Proposal

## Why

From 17.0 a localisation's tax report generates signed tax tags (`+mod303[01]`), and its tax templates
reference them. A database migrated from an older version keeps the unsigned tags of its first chart on
every tax repartition line and journal item.
- The native step that retags existing taxes is the chart template's reload; `l10n_es` runs it in
  `migrations/5.4/end-migrate.py`.
- OpenUpgrade 17.0 turns that step off (`openupgrade_framework/odoo_patch/odoo/modules/migration.py`).
- Its own script then tries to delete the old tags, and the foreign keys refuse.

So new invoices in 18 would carry grids no 18 report reads. On the first client, every tagged journal item
also carried every box of its tax, a union OpenUpgrade 13.0 left.

## What Changes

When the chain crosses 17.0, the target step, after the valuation alignment and before its checkpoint,
runs the target's Odoo to:
- run the chart template's own reload restricted to taxes. A tax whose template is unchanged gets its
  repartition lines' tags from the template; any other tax is left and listed;
- recompute every journal item's tax tags from repartition lines, as Odoo sets them when it posts. A tax
  line takes its repartition line's tags; a base line takes the tags of its taxes' base repartition lines
  for the document's type. Journal items of plain entries are left and counted;
- archive the tax tags that no repartition line or journal item uses and no tax report generates;
- keep nothing if any journal item's amount, taxes or sign would change;
- list everything in `logs/<target>-tax-grids.tsv`.

## Capabilities

### Modified Capabilities

- `migration-run`: the target step refreshes tax grids from the chart template.

## Impact

- New `odoo_dwg/taxgrids.py`, `odoo_dwg/templates.py`; tests in `tests/test_taxgrids.py`.
- Docs: `docs/migration/running.md`, `CHANGELOG.md`, `docs/project/roadmap.md`.
- Validated on the first client's migrated database: the boxes recomputed from the new grids match the
  filed VAT returns, except the differences its declarations dossier already attributes.
