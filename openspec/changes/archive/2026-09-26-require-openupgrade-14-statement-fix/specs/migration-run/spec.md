# Spec Delta

## MODIFIED Requirements

### Requirement: A known OpenUpgrade 14.0 defect on statement lines is repaired after its step

For a chain whose source is 13.0 or older, the driver SHALL check, with the 14.0 step's other
preconditions and before the step changes anything, that the OpenUpgrade checkout's account 14.0.1.1
post-migration holds the flush of the statement lines that OCA/OpenUpgrade#6005 added. When it does not,
the driver SHALL stop before the step, naming the pull request and the command that updates the checkout.

Right after the 14.0 step and its post hook, before neutralising and checkpointing, the driver SHALL count
the bank statement lines stored as reconciled whose move still has a line on the journal's suspense
account, with the same selection `migrate audit` uses. It SHALL record the check in the step record when
there are none, and stop the run, with the count, when there is any. It SHALL NOT recompute them. A chain
whose source is 14.0 or later SHALL NOT run the precondition or the check.

#### Scenario: A 12.0 source

- **WHEN** the driver of a 12.0 → 18.0 chain is generated
- **THEN** its 14.0 block checks the checkout for the fix before the step, and counts the lines after the
  post hook and before the checkpoint

#### Scenario: A checkout that predates the fix

- **WHEN** the 14.0 checkout's account post-migration lacks the flush
- **THEN** the run stops before the 14.0 step, naming OCA/OpenUpgrade#6005 and how to update the checkout

#### Scenario: A 14.0 source

- **WHEN** the driver of a 14.0 → 18.0 chain is generated
- **THEN** no step checks the checkout for the fix or counts the lines

#### Scenario: A resumed run

- **WHEN** a run resumes after the 14.0 checkpoint
- **THEN** the check does not run again, since the checkpoint already holds its result
