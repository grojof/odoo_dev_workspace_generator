# Proposal

## Why

The journal codes step renames only what the target refuses: shared codes, and codes that differ only by
case or spaces. The journal with most entries keeps its code. But a code the target accepts can still say
nothing. `BNK1`, `BNK2` and `CSH1` next to each other do not say which bank, company or card each one is.
On the first client, once the shared codes were settled, the natural next step was one readable scheme for
every bank, card and cash journal, such as bank journals numbered by company and age. The step could not express it: it ignored the
operator's code for a journal outside a group, and for the journal that keeps a group's code.

Renaming a readable code is optional. It is proposed after the first audit, and the client decides.

## What Changes

- The table the step writes and reads back accepts a code for **any** journal of the company, including
  the one that keeps a group's code. A journal outside every group shows up in the plan as renamed by
  the operator.
- A code equal to the journal's current code renames nothing.
- A new code that is another journal's current code is refused, naming both journals. The SQL checks
  each rename against the codes in use as it runs, so such a rename would depend on the order.
- Everything else is unchanged: generated proposals only for the groups the target refuses, the same
  validation (1 to 5 letters or digits, unique in the company), and the same guarded SQL.

## Capabilities

### Modified Capabilities

- `client-intake`: journal codes, renamed by the operator beyond what the target refuses.

## Impact

- `odoo_dwg/intake.py` (the plan), tests, `tools/verify_intake.py`, `docs/migration.md`, `CHANGELOG.md`.
