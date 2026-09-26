# Proposal

## Why

OpenUpgrade's 14.0 account migration stored bank statement lines still in the suspense account as
reconciled: an ORM flush wrote stale values over its own SQL. The driver repaired it after the 14.0 step
with Odoo's own recompute. The fix is now in OpenUpgrade itself: OCA/OpenUpgrade#6005 flushes the lines
before the SQL, merged into 14.0 on 2026-09-25. A repair of our own is no longer the answer; an
OpenUpgrade checkout that has the fix is.

## What Changes

- **Before the 14.0 step**, for a source up to 13.0, the driver checks that the OpenUpgrade checkout's
  `account/14.0.1.1/post-migration.py` holds the flush. It stops before the step when the checkout
  predates the fix, naming the pull request and the command that updates the checkout.
- **After the 14.0 step**, it no longer recomputes the lines. It counts the lines stored as reconciled
  whose move still has a line on the suspense account, the same selection `migrate audit` uses, and
  stops when there is any. With the fix there are none, so a count above zero is a defect nobody knows
  about yet, not something to repair silently.
- The SII certificate file is still carried after the 14.0 step, unchanged.

## Capabilities

### Modified Capabilities

- `migration-run`: the 14.0 statement-lines repair becomes a precondition on the OpenUpgrade checkout and
  a check after the step.

## Impact

- `odoo_dwg/templates.py` (the precondition, the check, the repair without the recompute),
  `tests/test_migration.py`, `tests/test_migration_audit.py`, `tools/verify_migration_driver.py`.
- Docs: `docs/migration/running.md`, `CHANGELOG.md`, `docs/project/roadmap.md`, `CONTRIBUTING.md`.
