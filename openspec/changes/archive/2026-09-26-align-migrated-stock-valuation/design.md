# Design

## The rule

For each company and each storable product that has layers or stock:
- **On hand**: the quants Odoo 18 values, in an internal location or a transit location with a company,
  with no owner other than the company (`stock.location._should_be_valued`,
  `stock.quant._should_exclude_for_valuation`).
- **Target**: on hand × `standard_price`, rounded in the company currency.
- **The layer**: `quantity = on hand − quantity_svl`, `value = target − value_svl`, `unit_cost` the cost,
  no move. Created only when either differs, beyond the unit of measure's rounding or the currency's.

Odoo's own `_change_standard_price` adds a value-only layer the same way. Emptying and refilling a
product's stock (`_svl_empty_stock`, `_svl_replenish_stock`) also moves quantity without a move.

## What it will not do

- **Automated valuation**: a layer there needs a journal entry, which the migration must not invent.
  Left and listed.
- **FIFO and lot valuation**: the layers' remaining values are the cost of what goes out next, and a flat
  alignment would rewrite it. Left and listed.
- **Journal entries or costs**: `account_move` is counted and `standard_price` fingerprinted before and
  after; any difference rolls everything back and stops the step.

## Why the target's Odoo and not SQL

The rules for what is valued and how much are Odoo's code, per version, and the layer's stored related
fields (`categ_id`) are filled by the ORM. The script needs 18.0 (`is_storable`, `lot_valuated`), hence
`target >= 18`.

## What differs from the source's figure

The source up to 12.0 valued `qty_available`, internal locations only. Odoo 18 also values a transit
location that has a company. A quant in transit makes the two figures differ by its value, and that
difference is data, not drift.
