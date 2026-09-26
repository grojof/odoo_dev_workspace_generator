# Spec Delta

## ADDED Requirements

### Requirement: Migrated payments are repaired after the target step

When the chain crosses 18.0, the target step SHALL, after its other repairs and before its checkpoint:

- remove each payment-order payment whose journal entry is not its order's, when exactly one other payment
  of the same bank payment line is on the order's own entry, and nothing points at it but its own links;
- give each posted payment that has no journal its payment order's journal, when that journal is a bank,
  cash or credit journal with one method line for the payment's method, without changing its journal entry;
- recompute every posted payment's state and reconciliation flags, then every posted invoice's payment
  status, with the target Odoo's own methods, again until neither changes, and at most five times;
- stop, keeping none of it, when any journal item's account, amount or reconciliation would change;
- list every payment removed, given a journal, or recomputed to another value, every payment left without a
  journal, and every invoice whose payment status changed, in `logs/<target>-payments-repaired.tsv`.

#### Scenario: A remittance whose line an operator's entry repeats

- **WHEN** a bank payment line has a payment on its order's entry and another on a manual entry that repeats
  its reference
- **THEN** the second payment is removed and listed, and no journal item changes

#### Scenario: A payment order posted through a miscellaneous journal

- **WHEN** a posted payment has no journal and its order's journal is a bank journal with a method line for
  its method
- **THEN** the payment gets that journal and method line, and its journal entry keeps its journal and name

#### Scenario: Payments left in process

- **WHEN** posted payments are `in_process` although their lines are reconciled
- **THEN** they are recomputed as Odoo computes them, and the invoices whose status changed are listed
