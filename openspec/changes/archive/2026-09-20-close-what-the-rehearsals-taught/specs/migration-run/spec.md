# migration-run Specification Delta

## ADDED Requirements

### Requirement: The driver honours what the operator decided

A module that resolves nowhere and has no successor is the operator's to answer for, and the answer is
recorded. That record SHALL be read by the **driver**, not only by the preflight action, from a known file
in the environment. Without it an operator could record a decision, watch the preflight accept it, and
still be refused by the run, which made the record inert exactly where it mattered.

A decision SHALL match the module under any name it carries in the chain — the one the operator started
with, the one a step knows it by, or the one it is about to become — because a rename does not make it a
different module and the operator copies whichever name they were shown.

An applied decision SHALL be named in the run's output, never applied silently. A decisions file that
cannot be read SHALL decide nothing.

#### Scenario: A module the operator decided to drop

- **WHEN** a module resolves in no step's sources and the environment's decisions file accounts for it
- **THEN** the run proceeds and says which decision it applied, with its reason

#### Scenario: An unreadable decisions file

- **WHEN** the decisions file is not valid JSON
- **THEN** it accounts for nothing, and a module nobody supplies still stops the run

### Requirement: Each step is judged against the database as it is then

The preflight reads the installed modules once, from the source database, so a module the chain installs
*along the way* is invisible to it — a module can appear in a repository at one step, be installed there
because its dependencies are present, and have gone from that repository by the next.

Each step SHALL re-read the installed modules from the working database before it runs, and SHALL judge
those the preflight did not account for. A module the preflight already judged SHALL NOT be judged again:
it would reach the same verdict twice, and re-judging it only widens what the gate lets through.

A step stopped this way SHALL stop at the step that found it, leaving the checkpoints before it intact.

#### Scenario: A module installed mid-chain that resolves nowhere

- **WHEN** a module not present in the source database is installed by an earlier step and resolves in no
  source of a later one
- **THEN** that later step stops before running, naming the module, and the earlier checkpoints remain

### Requirement: A step's log is read for the run that wrote it

Step logs are appended to and never rotated, so a step re-run after a failure carries every earlier attempt
in the same file. A report SHALL summarise each step's log within that step's own window, so that it does
not attribute a superseded attempt's errors to the latest run.

Odoo writes its log in UTC — it sets `TZ` on its own process — while the driver stamps its events in local
time with an offset, so the window SHALL be converted before comparing. A window that cannot be read SHALL
keep every line rather than hide them all.

#### Scenario: A step re-run after a failure

- **WHEN** a step failed, was fixed and re-run, and the report is read
- **THEN** that step is reported with what the successful run produced, not with the failed run's errors
