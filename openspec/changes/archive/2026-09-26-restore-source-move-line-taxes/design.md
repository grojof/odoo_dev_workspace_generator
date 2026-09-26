# Design

## Context

In `migration_invoice_moves`, OpenUpgrade 13.0:
1. matches invoice lines to journal items: strictly first, then relaxed. It sets `old_invoice_line_id` on
   each match;
2. inserts the unmatched invoice lines as new items;
3. adds to `account_move_line_account_tax_rel` the taxes of each item's invoice line, taken from the legacy
   `account_invoice_line_tax`, `ON CONFLICT DO NOTHING`.

Step 3 only adds. A reused item whose own taxes differed from its invoice line's keeps both sets.

What each item bore in the source cannot be read at 13.0 or later: the relation table now holds the union.
The source dump holds it, and the driver restores that dump into the working database at the start of every
fresh run.

## Goals / Non-Goals

**Goals:**
- Every reused item bears after the 13.0 step exactly the taxes it bore in the source, minus nothing and
  plus only what OpenUpgrade had no reason to add.

**Non-Goals:**
- Taxes OpenUpgrade or a later step changes on purpose: tax-group children the 13.0 repartition model no
  longer puts on items, taxes a localisation merges or renames. Those differ from the source without being
  in the invoice line's set, and stay.
- Items OpenUpgrade inserted: they have no source taxes. The grouped-items repair at the target keys them
  on their invoice line's own taxes.

## Decisions

**Keep the source's taxes at the source restore, not at the 13.0 step.**
- The 13.0 step itself makes the union, so its pre hook would be the latest moment.
- The source restore is the one point every fresh run passes through, and its checkpoint then carries the
  table to the 13.0 step on a resumed run too.
- It is one `CREATE TABLE … AS SELECT` over a relation table. The source's highest item id goes with it:
  an item with a higher id is one OpenUpgrade inserted.

**Take back right after the 13.0 step, not at the target.**
- At 13.0 the tax ids are still the source's.
- A later step may re-point an item to another tax. On the first client, a tax was replaced by another on a
  few items between 13.0 and 18.0. The source's ids would then no longer match, and a tax added by 13.0
  could escape.

**Take back only the added taxes that the invoice line bore.**
- That is exactly what step 3 can add. A tax an item gained for another reason is not in that set and stays.
- The alternative, resetting every reused item to its source set, would undo on purpose changes: the
  repartition model drops tax-group children from items.

**Drop the tables after the repair.** Nothing else reads them. A database the tool hands over should not
carry tables of the tool's own; the mail capture and neutralisation follow the same rule for their state.

**A missing table skips, and does not stop the run.**
- An environment whose source checkpoint predates this change would otherwise not run at all, although
  every other step is unaffected.
- The skip is printed with its remedy, and recorded in the step record as skipped.

## Risks / Trade-offs

- [The source's relation table is large] → It has two integer columns; one copy at restore time is seconds.
- [A resumed run from a checkpoint taken after the 13.0 step] → The repair is already in that checkpoint.
- [An environment that must repair its existing checkpoints] → It needs a run from the source dump; the
  skip says so.

## Migration Plan

An environment gets it when it is generated again. Its next run from the source dump keeps the taxes and
repairs them. Runs resumed from existing checkpoints skip the repair and say so.
