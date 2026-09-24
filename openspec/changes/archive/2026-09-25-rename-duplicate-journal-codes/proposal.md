# Proposal

## Why

Odoo declares a journal's code unique per company (`code_company_uniq`, `unique (company_id, code)`). A
database that already holds two journals with one code migrates without an error, and loses the constraint
for good. From 15.0 each step drops it and tries to add it again, fails, and only logs
`unable to add constraint 'account_journal_code_company_uniq'`. The first client's 12 → 18 rehearsal ended
that way. The migrated database accepted a duplicated code, and Odoo 18 builds new entry numbers from the
journal code (`_get_starting_sequence`). Codes that differ only by a trailing space do not break the
constraint, but they read as the same code everywhere.

## What Changes

A new step in **Migration → Take in a client copy**, **Find journal codes the target refuses**. It reads the
reference only and records:

- every group of journals of one company that share a code (the constraint breaks), and every group whose
  codes differ only by case or surrounding spaces (confusable);
- for each group, the journal that keeps its code (the one with most entries), and a proposed code for each
  of the others: at most 5 letters or digits, unique in the company;
- a table the operator may edit. The step reads the edited table back, keeps the operator's codes, and
  refuses one that is not 1–5 letters or digits or not unique;
- a guarded SQL file for the first step's pre hook. It changes the code column only, so existing entry
  numbers and sequences do not change, and only while the journal still has its old code and the new
  one is free.

## Capabilities

### Modified Capabilities

- `client-intake`: journal codes the target refuses.

## Impact

- `odoo_dwg/intake.py`: the query, the plan and the SQL (pure). `odoo_dwg/workflows/intake.py`: the step.
- Tests; `tools/verify_intake.py` against a real PostgreSQL (the constraint is added after the SQL runs).
- `docs/migration.md`, `docs/commands.md`, `CHANGELOG.md`, `docs/roadmap.md`.
