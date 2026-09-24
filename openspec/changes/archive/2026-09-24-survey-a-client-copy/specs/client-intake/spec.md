# Spec Delta

## ADDED Requirements

### Requirement: What the copy can act on is surveyed and recorded

The system SHALL offer an intake step that surveys the reference database, **reading only**, and records
as findings everything in it that can act on the outside world.

**Armed rules.** Each neutralisation rule with armed rows SHALL be recorded as one finding, holding:
- the rule;
- how many rows are armed;
- a sample of them;
- the severity the catalogue declares for that rule.

**Tables.** The survey SHALL also record:
- the active crons, with how overdue each one is. Every cron whose next call is already past fires at the
  first start;
- queued jobs, by channel and state;
- the outgoing mail queue, by state.

Mail that failed, and that a retry would send, SHALL be a finding of its own when there is any.

The survey SHALL connect as the database's owner: a role that cannot read secret columns cannot answer
it. If the survey cannot read something, it SHALL say "could not tell", never "clean".

#### Scenario: A production copy with crons and a tax integration armed

- **WHEN** the reference has active crons past their next call and a tax integration in production mode
- **THEN** each armed rule is a finding with its count and severity, and the crons are listed with how
  overdue each is

#### Scenario: Mail that failed for years

- **WHEN** the outgoing mail queue holds messages in the exception state
- **THEN** a finding records how many there are and the span of their dates, and says that a retry would
  send them

### Requirement: Every installed module is checked at every step, across all OCA repositories

For every installed module of Odoo or of OCA, the system SHALL record where its code is found at each step
of the chain, following the module's OpenUpgrade fate (renamed, merged, carried on). A module merged into
another needs its successor's code from the step of the merge onwards, not its own.

The code SHALL be looked for:
1. **in the core** of each step;
2. **in the OCA repositories the client uses**;
3. **in every OCA repository**, for the steps where step 2 left a gap. The list of repositories comes from
   GitHub's organisation listing.

Each OCA repository and version SHALL be read as a tree fetched without file contents, cached on the
host, and refreshed only on request. A branch that does not exist SHALL be recorded as absent, not
fetched again.

A module found at a step in no repository SHALL be a gap, recorded as a finding with the steps it is
missing from. A module found in a different OCA repository than it came from SHALL be recorded as moved.
Custom modules SHALL be listed as needing a port, not looked for.

#### Scenario: A module that moved repository

- **WHEN** an installed module lives in one OCA repository at 12.0 and in another from 14.0
- **THEN** it is found at every step, recorded as moved from 14.0, and is not a gap

#### Scenario: A module no OCA repository ports

- **WHEN** a module exists at 12.0 and in no OCA repository at 13.0 or later
- **THEN** it is a gap from 13.0, recorded in a finding that names every step it is missing from

#### Scenario: A module merged into another

- **WHEN** OpenUpgrade declares a module merged into a successor at 15.0
- **THEN** its code is looked for under its own name at 13.0 and 14.0, and under the successor's name
  from 15.0

### Requirement: The client's own code is scanned for network calls, and the scanner is shown to work

The system SHALL scan the Python code of every installed module that is neither Odoo's nor OCA's. It
SHALL look for imports and calls that reach the network or start processes. Each hit SHALL be recorded
with its file, line and pattern.

Before scanning, the system SHALL run every pattern against a declared positive control: one line each
pattern must match. If any pattern fails its control, the system SHALL refuse to report a result, rather
than report a scan that found nothing because it could find nothing.

#### Scenario: Custom code that calls out

- **WHEN** a custom module imports `requests` and calls `requests.post`
- **THEN** the hit is recorded with file, line and pattern, in a finding for that module

#### Scenario: A broken pattern

- **WHEN** a pattern no longer matches its control line
- **THEN** the step refuses to report, naming the pattern, and records no "nothing found"
