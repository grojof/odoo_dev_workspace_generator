# Spec Delta

## ADDED Requirements

### Requirement: Stock valuation layers are aligned to on-hand quantity and cost after the target step

For a source up to 12.0 and a target from 18.0, the target step SHALL, after the payments repair and before
its checkpoint, run the target's Odoo to add one valuation layer per storable product with periodic
valuation whose layers' quantity or value differs from its stock on hand, as Odoo values it, at its cost.
The layer SHALL carry that difference, the product's cost and the description "Migration: align to on-hand
quantity and cost". For an average-cost product the layer SHALL hold the remaining quantity and value, and
the earlier layers none.

It SHALL leave, and list, products with automated valuation, FIFO or lot valuation. It SHALL keep nothing
when a journal entry would be created, a cost would change, or an adjusted product would not end at on-hand
quantity times cost. It SHALL list every product aligned, with its quantity and value before and after, and
every product left, in `logs/<target>-valuation-aligned.tsv`.

#### Scenario: Layers rebuilt with drift

- **WHEN** a product's layers hold more value than its stock on hand times its cost
- **THEN** a labelled layer brings them to that value, and no journal entry is created

#### Scenario: Automated valuation

- **WHEN** a product's category values it in real time
- **THEN** its layers are left as they are and the product is listed

#### Scenario: A second run

- **WHEN** the alignment runs on a database it already aligned
- **THEN** it adds no layer
