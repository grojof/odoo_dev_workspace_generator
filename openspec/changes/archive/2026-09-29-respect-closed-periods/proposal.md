# Proposal

## Why

Two target-step repairs rewrite journal items of every period: the grouped invoice items (the amounts move
from the grouped item to the invoice lines) and the tax grids (every invoice item's tags recomputed). Net
balances, tax bases and declared amounts do not change, but a closed and declared year's journal detail
does: on the first client, the gross debit and credit of several accounts rose in every closed year, and
thousands of moves have another number of items. OpenUpgrade's maintainers advise against changing closed fiscal
years (OCA/OpenUpgrade#3054), and OCA's `account_chart_update` retags taxes, never past journal items. An
independent review of the procedure flagged both as what a standard OCA integrator would not do.

## What Changes

- **Closed periods are the company's lock dates**: a move dated on or before the later of
  `fiscalyear_lock_date` and `tax_lock_date` (`lockdates.py`). With neither set, no period is closed.
- **Grouped invoice items**: only invoices of open periods, or still open, are repaired. A paid invoice of
  a closed period keeps OpenUpgrade's result, and the repair counts them.
- **Tax grids**: repartition lines are retagged as before; journal items are regridded only in open
  periods, and the closed periods' items are counted as kept.

Out of scope: an option to repair closed periods too. If a client's accountant approves it in writing, it
can be added then.

## Capabilities

### Modified Capabilities

- `migration-run`: both repairs leave closed periods.

## Impact

`odoo_dwg/lockdates.py` (new), `odoo_dwg/ungroup.py`, `odoo_dwg/taxgrids.py`; tests; the verifier of
grouped invoice lines; docs.
