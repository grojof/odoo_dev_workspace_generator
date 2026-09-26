# Proposal

## Why

A migrated database's payments are wrong in three ways that no step repairs, and all three were measured on
the first client's database:

- **Duplicate payments.** OCA `account_payment_order` 14.0 creates one `account.payment` per bank payment
  line, joining the journal items that carry the line. When an operator's own entry repeats a line's
  reference (an expense or reversal of a remittance), the join yields one payment per entry: the first client
  had dozens of extra payments, counted twice in every payment list. No journal item points at them.
- **Payments without a journal.** OpenUpgrade 18.0 fills `account_payment.journal_id` from the entry's
  journal only when that journal is a bank, cash or credit one. A payment order posted through a
  miscellaneous journal leaves its payments with none, though Odoo 18 requires it.
- **Every payment "in process".** OpenUpgrade 18.0 sets `state` to `paid` only when the entry's
  `payment_state` is `paid`, which a payment's entry never is in 17. Nothing recomputes it, and the
  reconciliation flags of the payment-order payments inserted at 14.0 are empty.

## What Changes

After the target step, for a chain that crosses 18.0, the driver:
- removes a payment-order payment whose entry is not its order's, when another payment of the same bank
  payment line is on the order's own entry, and only when nothing but its own links points at it;
- gives a payment with no journal its payment order's journal and that journal's method line for the
  payment's method, in SQL: an ORM write would rewrite its entry;
- recomputes every posted payment's `state`, `is_reconciled` and `is_matched`, then every posted invoice's
  `payment_state`, with Odoo's own methods, and stops, keeping nothing, if any journal item's amount,
  account or reconciliation changed;
- lists what it changed in `logs/<target>-payments-repaired.tsv`.

## Capabilities

### Modified Capabilities

- `migration-run`: the target step repairs the migrated payments.

## Impact

- New `odoo_dwg/payments.py` (the SQL and the recompute script), `odoo_dwg/templates.py` (the repair at the
  target step).
- Tests: `tests/test_payments.py`. New `tools/verify_migrated_payments.py` (the SQL against a throwaway
  PostgreSQL); `tools/verify_migration_driver.py` (the repair's place).
- Docs: `docs/migration/running.md`, `CHANGELOG.md`, `docs/project/roadmap.md`, `CONTRIBUTING.md`,
  `AGENTS.md`.
- Validated on the first client's migrated database: duplicates removed, journals given, every posted payment
  recomputed, the invoices whose status changed listed, no journal item changed.
