# Design

## Where

At the target step, after the grouped-items repair and before the checkpoint, when the chain crosses 18.0
(`source < 18 <= target`). The duplicates and the journals are SQL, in one transaction with its checks.
The recompute runs in the target's `odoo-bin shell`, because the rules are Odoo's own code, and computing
them in SQL would be a copy that drifts.

## Duplicates

The OCA 14.0 migration (`account_payment_order/migrations/14.0.2.0.0/post-migration.py`) inserts one
payment per `bank_payment_line`, with a `LEFT JOIN` on the journal items that carry the line. It records the
line in `account_payment.old_bank_payment_line_id`. For a line with several payments, the one to keep is on
the order's own entry (`account_move.payment_order_id = account_payment.payment_order_id`). The others are
removed only when:
- exactly one payment of that line is on the order's entry;
- no journal entry names them as its payment (`account_move.origin_payment_id`), no journal item
  (`account_move_line.payment_id`), no statement line, no transaction, no other payment;
- their remaining links are to their own entry (`account_move__account_payment`) and to payment lines their
  kept twin also has.

Anything else about a line is left as it is and listed.

## Journals

For a posted payment with no journal and a payment order: the order's journal, when it is a bank, cash or
credit journal and has exactly one method line for the payment's method. The journal is written in SQL,
since `account.payment.write` of `journal_id` synchronises the entry, renaming it and rebuilding its lines.
A payment with no order, or an order whose journal fits none, is left and listed.

## The recompute

`env.add_to_compute` of `state`, `is_reconciled`, `is_matched` on the posted payments, then `flush_all`;
then the same for `payment_state` on the posted invoices. No `write`, so no tracking message and no entry
synchronisation. Before and after, an md5 over every journal item's id, account, debit, credit, residual
and reconciliation: when it differs, the transaction is rolled back and the step fails. The payments and
invoices whose values changed are listed, by id and name, with before and after.

A payment's state reads its invoices' payment status (`_compute_state` depends on
`reconciled_invoice_ids.payment_state`), and an invoice's reads its payments'. A recompute assigns in
protected mode and does not carry one into the other, so both run again until neither changes: at most
five rounds, or nothing is kept. On the first client it settled after two, and a second run changed
nothing.

On the first client, Odoo's rules gave:
- every posted payment `paid`, except one batch payment still `in_process`: its bank line is unmatched,
  and some of the bills it paid are reversed, so not all are `paid`;
- invoices settled only by credit notes, and credit notes settled only by journal entries, from `paid` to
  `reversed` (`account_move.py` `_compute_payment_state`);
- no invoice `in_payment`.
