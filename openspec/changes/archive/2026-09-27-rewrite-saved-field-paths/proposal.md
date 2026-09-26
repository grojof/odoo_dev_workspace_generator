# Proposal

## Why

`migrate audit` finds saved filters and exports naming fields the target lacks (change
`audit-saved-field-paths`). Most of those fields have a successor the chain moved their data to. On
the first client's migrated database, all but one of the saved filters and exports broken by Odoo's
standard changes had one:
- invoice fields went from `account.invoice` to `account.move`;
- `qty_done` became `quantity`;
- `move_lines` became `move_ids`;
- the partner flags became ranks;
- the journal's two default accounts became one;
- account types became a selection.

Left as they are, every user has to save them again.

## What Changes

For every chain, after the menu references, the target step rewrites saved filters and export
columns through `odoo_dwg/savedpaths.py`:
- a field whose target successor is proven from the sources is renamed, following each path through
  the target's relations;
- a domain value takes its successor's value where the successor maps values (an account type);
- a condition takes its successor's condition where no single field replaces it (an invoice line's
  invoice, a reference split between vendor and customer documents, a partner flag become a rank);
- an export column with no successor is dropped, and columns that end up the same are kept once;
- a filter with anything it cannot rewrite is left whole;
- a model that is gone leaves its filters and exports as they are.

Everything is listed in `logs/<target>-saved-paths.tsv`.

## Capabilities

### Modified Capabilities

- `migration-run`: the target step rewrites saved filters and exports whose fields the chain renamed.

## Impact

- New `odoo_dwg/savedpaths.py`; `odoo_dwg/templates.py`; tests in `tests/test_savedpaths.py`.
- Docs: `docs/migration/running.md`, `docs/migration/checks-findings.md`, `CHANGELOG.md`,
  `docs/project/roadmap.md`.
