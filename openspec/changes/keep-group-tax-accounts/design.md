# Design

## Decisions

- **The children's accounts, not the template's.** The database's own accounts are what the source used: a
  company may keep its own account on a child tax. `account_chart_update` would replace it with the
  template's; the migration has to keep what was there.
- **From the child's repartition line.** OpenUpgrade 13.0 gives each child its repartition lines with its
  accounts, and matches the journal items from the child's line to the group's by repartition type and
  sign. The same match, with the document (invoice or refund), gives each group line its account, with no
  rule of our own.
- **Only lines without an account.** Idempotent, and a no-op once OpenUpgrade sets them itself.
- **At the 13.0 step.** The children are dropped from later templates and may be archived or cleaned
  afterwards; right after the step they and the filiation table are intact, as for the taxes taken back.
