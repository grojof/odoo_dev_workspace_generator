# Spec Delta

## ADDED Requirements

### Requirement: A known OpenUpgrade 14.0 defect on statement lines is repaired after its step

For a chain whose source is 13.0 or older, the driver SHALL recompute, right after the 14.0 step and its
post hook and before neutralising and checkpointing, the `is_reconciled` and `amount_residual` of the bank
statement lines stored as reconciled whose move still has a line on the journal's suspense account: the
only lines the defect can leave wrong. It SHALL select them in SQL, and recompute them with Odoo's own
method through `odoo-bin shell` on the step's Odoo, venv and config, with HTTP off. It SHALL print how many
lines it selected and how many are still reconciled after, record the repair in
the step record, and stop the run if the repair fails. A chain whose source is 14.0 or later SHALL NOT run
it.

#### Scenario: A 12.0 source

- **WHEN** the driver of a 12.0 → 18.0 chain is generated
- **THEN** its 14.0 block recomputes the statement lines' flag after the post hook and before the checkpoint

#### Scenario: A 14.0 source

- **WHEN** the driver of a 14.0 → 18.0 chain is generated
- **THEN** no step recomputes the flag

#### Scenario: A resumed run

- **WHEN** a run resumes after the 14.0 checkpoint
- **THEN** the repair does not run again, since the checkpoint already holds its result
