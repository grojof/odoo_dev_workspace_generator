# Spec Delta

## ADDED Requirements

### Requirement: The operator's SQL runs around a step when there is some

A client's data can break a migration script that no source anticipates. What to do about it is a
decision about that client's data. The driver SHALL therefore run the operator's own SQL around a step:
- `hooks/<version>-pre.sql` before the step;
- `hooks/<version>-post.sql` after the step succeeds and before its checkpoint, so the checkpoint holds
  what the post-step hook restored.

Each file SHALL run in one transaction and stop at its first error. A hook that fails SHALL stop the run
and name the file. Each hook that runs SHALL be named in the output and recorded in the step log. A step
with no hook file SHALL run as before.

#### Scenario: Accounts a migration script needs for a moment

- **WHEN** `hooks/14.0-pre.sql` records some deprecated accounts and makes them usable, and
  `hooks/14.0-post.sql` deprecates exactly them again
- **THEN** the driver runs the first before step 14.0 and the second after it, before its checkpoint, and
  names both

#### Scenario: A hook that fails

- **WHEN** a pre-step hook fails
- **THEN** the run stops before the step, names the file, and writes no checkpoint for that step
