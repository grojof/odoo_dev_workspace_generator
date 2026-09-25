# Proposal

## Why

Up to 13.0 a bank statement line never reconciled has no journal entry. OpenUpgrade's 14.0 account
post-migration creates one for each such line through the ORM (`fill_statement_lines_with_no_move`). It
then computes the lines' `is_reconciled` and `amount_residual` in raw SQL
(`fill_account_bank_statement_line_reconciliation`), with no flush in between. The ORM still holds the
values it computed when each move had no suspense line yet (`is_reconciled = True`), and a later flush
writes them over the SQL result.

Lines still waiting in the suspense account are then stored as reconciled, and the reconciliation screen,
which filters on that field, does not show them. On the first client's copy it hit part of such
lines in one run and all of them in another. Replaying OpenUpgrade's own SQL on the step's checkpoint
gives the right value for every wrong line. Odoo's `_compute_is_reconciled` is the same in 14.0 and 18.0,
apart from the name of the "to check" flag, and recomputing with it fixes exactly those lines.

## What Changes

For a chain whose source is 13.0 or older, the driver repairs the flag right after the 14.0 step, before
its checkpoint. It selects in SQL the lines stored as reconciled whose move still has a suspense line,
the only ones the defect can leave wrong. It then runs `odoo-bin shell` on the step's own Odoo and
recomputes their `is_reconciled` (and `amount_residual`) with Odoo's own method, and prints how many
lines it selected and how many are still reconciled after. The repair is recorded in the step record and named in the log. It is
idempotent, and harmless once OpenUpgrade flushes itself.

## Capabilities

### Modified Capabilities

- `migration-run`: a known OpenUpgrade 14.0 defect repaired after its step.

## Impact

- `odoo_dwg/templates.py` (driver), tests, `tools/verify_migration_driver.py`, `tools/verify_generated_shell.py`.
- `docs/migration.md`, `CHANGELOG.md`, `docs/roadmap.md`.
- Upstream: an OpenUpgrade issue and pull request (a flush after the loop), prepared separately.
