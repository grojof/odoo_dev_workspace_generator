# Design

## The proof

1. **A statement is trusted only if it matches its file.** `balance_start + sum(lines) =
   balance_end_real`. The balances come from the bank's file, so a statement that matches them holds
   exactly the file's movements.
2. **A bank day is a statement's lines on one date.** Its content signature is the sorted list of
   the lines' fingerprints (journal, date, amount, `name`, `ref`, `note`, `partner_name`). Its
   end-of-day balance is `balance_start` plus the running sum of the statement's days up to it.
3. **Two trusted statements of the same journal holding the same day with the same content and the same
   end-of-day balance hold the same bank day.** Different real movements would give either a different
   content or a different balance.
4. Within such a day, each movement is its fingerprint plus its occurrence index, so a legitimate repeat
   inside the day (two equal fees) is two movements, not one. Of each movement's copies, one is kept: a
   reconciled one if any, else the lowest id. Every other copy is a duplicate. An unreconciled one is
   certain and harmless to drop. A reconciled one means the movement was reconciled twice.

Repeats between statements that fail step 1, or whose balances differ, are not proven and are not
listed.

## One query, no temporary tables

The reader role cannot be assumed to create temporary tables, so the query is one `SELECT` with CTEs.
On a client copy with tens of thousands of lines it takes a few seconds.

## Nothing is deleted by the step

The duplicates are dropped on the working copy before the chain, by SQL the operator chooses to run, in the
first step's pre hook. The file the step writes deletes a line only if it still has no journal item and its
kept twin still exists with the same fingerprint. So it is idempotent, and harmless on a later copy where
ids moved on. The step must be re-run on the final copy.

## Sources from 14.0

There, every statement line already has an entry. A duplicate is then an accounting error in the client's
books, not a migration effect, and the query's reconciliation test differs. Out of scope: the step says so
and stops.
