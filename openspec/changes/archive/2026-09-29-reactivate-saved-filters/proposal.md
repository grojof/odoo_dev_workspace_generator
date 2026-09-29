# Proposal

## Why

OpenUpgrade archives, at every step, each active saved filter whose domain or grouping no longer loads
(`disable_invalid_filters`, in the base end-migration of each version). The target step then rewrites
filters whose fields the chain renamed, and the client-modules stage's hook moves filters to the fields
that replace a retired module's, but nothing reactivates them. On the first client, every filter the
target step rewrote was archived at the target, while none was archived in the source: users would not
see them, and the report said they work.

## What Changes

- **The source's active filters are kept** at the source restore, in a table of the tool's own.
- **After the rewrite, and at the end of the client-modules stage**, every kept filter the chain archived
  is reactivated, then OpenUpgrade's own check runs on the active filters, so one still invalid is archived
  again by the same rule. Each filter reactivated or left archived is listed in
  `logs/<step>-saved-filters.tsv`.
- **A filter saved on a window action the chain deleted** (Odoo 12's four invoice actions) first moves
  to the target's action for the same documents.
- **A filter the operator archived in the source stays archived.**
- **The tool's kept tables are dropped** from the working database when the run completes; the
  checkpoints keep them for a resumed run and `--redo-modules`. An independent review found four of them
  left in the final database.

## Capabilities

### Modified Capabilities

- `migration-run`: the saved-paths requirement reactivates the filters the chain archived.

## Impact

`odoo_dwg/savedpaths.py`, `odoo_dwg/templates.py`; tests in `tests/test_savedpaths.py`; docs.
