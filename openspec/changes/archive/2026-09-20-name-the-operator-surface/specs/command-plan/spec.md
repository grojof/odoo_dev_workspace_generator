# command-plan Specification Delta

## ADDED Requirements

### Requirement: Plan, preview, confirm, apply

No action SHALL mutate the host outside a plan that has been previewed and confirmed. A plan is assembled by
a pure planner and is the only thing in the tool that runs a command.

The preview SHALL show every step in order, numbered, with its description and the exact command text,
wrapped to the terminal — the command as it will run, not a summary of it. Applying SHALL be declined by
default: the operator says yes. An action that destroys data or is otherwise not undoable SHALL additionally
require the operator to type an exact phrase, and that question SHALL name what is about to go.

#### Scenario: Nothing runs unconfirmed

- **WHEN** a plan is assembled
- **THEN** every command is printed before any of them runs, and the default answer applies none

#### Scenario: A destructive action names what it takes

- **WHEN** the operator asks to delete something the tool cannot recreate
- **THEN** the confirmation names it, and nothing is applied until the exact phrase is typed

### Requirement: A plan reports per step and stops at the first failure

Applying SHALL print one line per step with its outcome, and SHALL stop the whole plan at the first step
that exits non-zero: a later step's success would otherwise be reported against a host the earlier step did
not change.

A failing step SHALL print the end of its output, which is where the reason is. A step that succeeds SHALL
still surface the lines it printed that name a warning, a deprecation, an error or a failure, bounded so
that one noisy step cannot bury the rest of the plan. With verbose output selected (`--verbose`, or
`ODWG_VERBOSE=1`) every line SHALL appear live instead, which is what a long clone or install looks like
while it works.

Steps SHALL run with their input closed. A step that waited for input would otherwise block behind output
the operator cannot see, and would eat what they typed next.

#### Scenario: A failing step stops the plan and says why

- **WHEN** step 4 of a twelve-step plan exits non-zero
- **THEN** the end of its output is printed, the plan stops, and steps 5 to 12 do not run

#### Scenario: A warning from a successful step is not lost

- **WHEN** a step succeeds after printing a deprecation warning
- **THEN** that line is shown under the step, although the step is reported OK

#### Scenario: A step cannot swallow the operator's keystrokes

- **WHEN** a step runs a command that would prompt
- **THEN** it reads end-of-input rather than the terminal, and the plan does not stall on an invisible prompt

### Requirement: An interrupted plan leaves no half-written artifact

Every artifact a plan writes SHALL become visible only complete.

A generated file SHALL be written beside its target and renamed over it in the same step that sets its mode,
so no reader — including a script the plan is regenerating while that script is running — ever sees a partial
file, or one that exists without its mode. A clone SHALL be fetched into a sibling path and renamed on
success, so an interrupted clone leaves nothing at the final path that a later run would skip as present. A
build that installs into a directory SHALL be marked ready only once every install in it has finished, and
later runs SHALL skip it on that mark, never on the directory's existence. A dump written as a checkpoint
SHALL be written to a temporary name and renamed, for the same reason.

#### Scenario: Regenerating a script that is running

- **WHEN** the plan rewrites a script that a shell is currently executing
- **THEN** the running shell keeps reading the file it started with, because the new one arrives by rename

#### Scenario: An interrupted clone is redone

- **WHEN** a clone is interrupted after fetching objects
- **THEN** nothing sits at the clone's final path, and the next plan clones it again

#### Scenario: A half-built venv is not reused

- **WHEN** a venv build is interrupted between creating the environment and installing into it
- **THEN** the next run rebuilds it, because the ready mark was cleared first and never written
