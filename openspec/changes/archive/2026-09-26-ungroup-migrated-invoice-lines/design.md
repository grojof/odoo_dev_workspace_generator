# Design

## Context

What the source and OpenUpgrade leave behind:

- **12.0 source.** A posted invoice's journal items may be grouped per account and taxes.
- **OpenUpgrade 13.0** (`account/migrations/13.0.1.1/post-migration.py`, `migration_invoice_moves`):
  - it matches the items to invoice lines where it can;
  - it sets `exclude_from_invoice_tab` on every item of an invoice without an invoice line of its own
    (grouped items, and also receivable, payable, tax and anglo-saxon lines);
  - it inserts each unmatched invoice line with a zero balance and `old_invoice_line_id`;
  - it adds each matched item's invoice-line taxes to the taxes the item already had, so a reused item can
    carry the union of a group's taxes;
  - the legacy `account_invoice_line_tax` table stays in the database.
- **OpenUpgrade 16.0** (`account/16.0.1.2/pre-migration.py`, `_account_move_fast_fill_display_type`) types
  every invoice item that is neither a tax nor a receivable or payable line as `product`.
- **At the target**, `exclude_from_invoice_tab` survives as a column with no field.

The OCA AEAT declarations and the VAT book select lines by their taxes (`tax_ids`, `tax_line_id`) and sum
signed balances. So a repair that keeps, per move, each tax's signed sum cannot change a declaration.

## Goals / Non-Goals

**Goals:**
- Every grouped item whose invoice lines are known is replaced by those lines' own amounts.
- Balances by account, by partner and by tax are invariant by construction, and checked.

**Non-Goals:**
- Tags: the lines' tax tags stay as migrated.
- Moves in a foreign currency: their rate would have to be reproduced per line.
- Anglo-saxon cost lines that OpenUpgrade 16.0 also typed as `product`: they have no invoice line, so no
  group matches them, and they are left untouched.

## Decisions

**The unit is a group: move, account and taxes, not the whole invoice.**
- Moving an amount inside such a group cannot change an account's, a partner's or a tax's sum. The
  alternative, pairing by account only, was measured on the first client's database: a few filed VAT
  returns changed by a few euros, because OpenUpgrade 13.0 had given some lines the union of the group's
  taxes.
- Pairing by group also lets a move with one odd group still have its other groups repaired.

**A zero-amount line keys on its source invoice line's taxes.**
- The legacy `account_invoice_line_tax` table holds each invoice line's own taxes. A zero-amount line that
  OpenUpgrade gave the union takes back its own set. Changing a zero-amount line's taxes changes no sum.
- A reused matched item (non-zero) is never re-taxed. Re-taxing one, tried first, moved a filed VAT
  return's base by tens of euros.

**The direction comes from the document, not from the grouped item's sign.**
- A vendor bill and a customer refund debit their lines; the others credit them.
- Taking the sign of the grouped item fails when the group nets to zero. The first client's import
  invoices had +X under one tax and −X under another on one account.

**Links are found by foreign key, and a link that is not understood keeps the group grouped.**
- The repair reads every foreign key pointing at `account_move_line`.
- A pure link table (two columns) is copied to every line of the group. The move line's own taxes and tags
  tables are excluded, since the lines keep their own.
- The known single references move to the group's largest line: the analytic line, and the EC sales list
  record and refund details.
- Any other reference to a grouped item leaves its group grouped and is named. The alternative, moving
  every reference, could re-point a reconciliation.

**An open item on a reconcilable account is repaired; a reconciled one is not.**
- An unreconciled item's open amount is its balance. Each line takes its own amount as open, so what is
  open per account and partner is unchanged, and that is checked.
- An item reconciled, partly or fully, is left: its reconciliation would have to be split. On the first
  client, the items on a reconcilable account were prepaid expenses, none reconciled.

**SQL in one transaction, with the checks as assertions.**
- It runs through `psql` with `ON_ERROR_STOP`. The checks raise, so a failed check rolls everything back.
- Not the ORM: `odoo-bin shell` would load the registry and recompute fields for tens of thousands of
  lines, and the rule itself is plain arithmetic.
- The before-snapshots are taken only on the affected moves.

**At the target step, not at 16.0.**
- It was validated at the target, by recalculating every filed VAT return and EC sales list before and
  after on the first client's 18.0 database.
- Later OpenUpgrade steps read these lines as they are. No step after 16.0 needs them ungrouped.

## Risks / Trade-offs

- [A module keeps its own reference to a journal item] → The group stays grouped and is named with the
  table, so the operator can extend the list.
- [A check is too strict on a legitimate case] → The whole repair rolls back and the run stops with the
  check's name. The target checkpoint is not written, and a fix plus `--resume` retries it.
- [Performance on large databases] → The snapshots are limited to the affected moves. On the first client
  (tens of thousands of grouped items) the whole repair took about two minutes.

## Migration Plan

An existing environment gets it when it is generated again, which rewrites the driver. A run already past
its target checkpoint does not repeat it: removing the target checkpoint (and the client-modules one)
makes the next `--resume` run the target step again, repair included. `run_migration.sh --redo-modules`
does not re-run it, since it restores from the target checkpoint.
