# Design

## Decisions

- **OpenUpgrade's own check decides validity.** Reactivating every candidate and then calling
  openupgradelib's `disable_invalid_filters` on the target applies exactly the rule that archived them: a
  domain `search_count` inside a savepoint, and the grouping keys of the context checked against the
  model's fields. A rule of our own would drift from it. openupgradelib is in every step's venv; outside
  the OpenUpgrade framework its `target_version` guard is unset, so it runs.
- **Candidates are the source's active filters with a domain.** OpenUpgrade only checks filters whose
  domain is not `[]`, so it never archived the others; a filter archived by the operator is not a
  candidate.
- **Twice.** The target step's rewrite repairs filters naming renamed fields; the modules stage's hook and
  its installs repair those naming a retired module's fields. Running after both, with the same candidates,
  is idempotent, and the stage's run is what the final database shows.
- **The kept table stays in the target checkpoint**, since `--redo-modules` starts from it; the driver's
  final cleanup drops the tool's kept tables from the working database.
