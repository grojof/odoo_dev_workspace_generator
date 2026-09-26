# Proposal

## Why

Up to 12.0 a product's value is its stock on hand times its cost. OpenUpgrade 13.0 builds the valuation
layers by replaying moves and price history, and two flaws of that replay leave the layers' value away
from quantity times cost:
- a receipt counted twice (its own averaged cost in the price history, a moment before the move);
- value left on no quantity when a receipt brings negative stock back to zero.

The layers' quantity can also differ from the stock on hand where the source's quants and moves already
disagreed. Odoo 18 values products from their layers, so its valuation screens show neither the source's
figure nor the stock there is. Its average cost would take the drift in too: it divides the layers'
value by their quantity.

## What Changes

For a source up to 12.0 and a target from 18.0, after the payments repair and before the checkpoint, the
target's own Odoo adds one layer per storable product whose layers differ from its stock on hand at its
cost. The layer is labelled "Migration: align to on-hand quantity and cost", and brings quantity and value
to what is on hand, valued by Odoo's own rules, at the product's cost.
- Average-cost products get their remaining quantity and value on the new layer, as emptying and
  refilling the stock does.
- Only periodic valuation: a product with automated valuation, FIFO or lot valuation is left and listed.
- Nothing is kept if a journal entry would appear, a cost would change, or a product would not end
  aligned.
- Every product aligned or left goes to `logs/<target>-valuation-aligned.tsv`.

## Capabilities

### Modified Capabilities

- `migration-run`: the target step aligns the stock valuation layers a source up to 12.0 gets.

## Impact

- New `odoo_dwg/valuation.py`, `odoo_dwg/templates.py`; tests in `tests/test_valuation.py`.
- Docs: `docs/migration/running.md`, `CHANGELOG.md`, `docs/project/roadmap.md`.
- Validated on the first client's migrated database with its Odoo 18.
