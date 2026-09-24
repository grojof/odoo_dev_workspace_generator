# Proposal

## Why

Up to 13.0, a bank statement line that was never reconciled has no journal entry. OpenUpgrade's 14.0
step creates one for every such line (bank against the suspense account). Its maintainers treat that as
the expected result (OCA/OpenUpgrade#3056, #3251), and it has no switch. A statement imported twice
therefore becomes, in 14.0 and later, bank movements that never happened. That is easy to do: the Norma 43
import sets no `unique_import_id`, so Odoo cannot see a repeated file. The first client's copy had
many such lines, some twice-imported movements reconciled in both copies, and nothing to tell them
from legitimate repeats (two equal fees on one day) except the bank's own balances.

Matching amount, date and label is not proof. The proof is in the statements themselves. Each statement
carries the bank's opening and closing balance from the file. A day that appears in two statements of the
same journal, with the same movements and the same end-of-day bank balance, is one bank day imported
twice.

## What Changes

A new step in **Migration → Take in a client copy**, **Find bank statement lines imported twice**. It
reads the reference only, for a source up to 13.0, and records:

- whether each statement matches its file: opening balance + lines = closing balance;
- the **certain duplicates**: the unreconciled lines of a bank day that appears in two or more
  statements that match their files, with identical day content (journal, date, amount, label, reference,
  note, partner name) and the same end-of-day balance. One copy of each movement is kept, a reconciled
  one if there is one;
- the movements **reconciled in more than one copy**: the books already carry them twice, which is the
  client's accountant's to correct;
- how many unreconciled lines remain, and how many of them fall after the company's lock date.

It writes a data table, a guarded SQL file the operator may put in the first step's pre hook, and one
finding. It deletes nothing. Repeats that the balances cannot prove are left alone.

## Capabilities

### Modified Capabilities

- `client-intake`: finding bank statement lines imported twice.

## Impact

- `odoo_dwg/intake.py`: the query, the summary, the guarded SQL (pure).
- `odoo_dwg/workflows/intake.py`: the step.
- Tests, and `tools/verify_intake.py` against a real PostgreSQL.
- `docs/migration.md`, `docs/commands.md`, `CHANGELOG.md`, `docs/roadmap.md`.
- Out of scope: sources from 14.0, where every line already has its entry; deleting anything.
