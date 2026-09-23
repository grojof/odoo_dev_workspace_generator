# Spec Delta

## ADDED Requirements

### Requirement: The working database is neutralised, and never given back, by the driver

The driver SHALL neutralise the working database at three points:
- after restoring the source dump, before the first step runs;
- after each successful step, before it takes that step's checkpoint;
- after restoring a checkpoint to resume, before the next step runs.

It SHALL use the same catalogue and record as the menu action, so that re-neutralising after a step
records only what that step introduced.

The driver SHALL NOT restore production settings at any point. A migrated database, and every checkpoint,
SHALL be neutralised when it is opened for testing. Restoring is the operator's explicit action.

A neutralisation that fails SHALL stop the run before the step or the checkpoint that would follow it. A
database that could not be neutralised is not one to run Odoo on or to hand on as a checkpoint.

#### Scenario: A checkpoint opened for testing

- **WHEN** the 16.0 checkpoint of a 12 → 18 run is restored and started to look at it
- **THEN** its crons, including any the 13.0–16.0 steps created, are inactive, and the check reports
  nothing can act

#### Scenario: The chain finishes

- **WHEN** the last step of the chain succeeds
- **THEN** the working database is neutralised after it, and the driver ends without restoring anything

### Requirement: A migrated database is opened for testing only through a guarded start

The migration environment SHALL include a script that starts Odoo, at a version of the chain, on a chosen
database of that environment: the working database, or a database restored from a checkpoint. Opening a
migrated database or a checkpoint for testing SHALL go through this script, which on every start:

1. **Re-neutralises** the database, which covers what an install, update or migration step switched back
   on since the last start.
2. **Runs the check.** If anything can still act on the outside, it refuses to start, naming what can act.
3. **Starts Odoo with cron threads at zero**, listening on loopback only, with the step's add-ons and the
   mail sent to the local capture. A cron that a module installed during this session creates, or
   switches on, cannot run until the next start neutralises it.

The script SHALL NOT restore production settings, and SHALL offer no option that skips the
re-neutralisation or the check.

#### Scenario: A module installed while testing

- **WHEN** the operator installs a module from the interface of a migrated database opened through the
  script, and that module creates an active cron
- **THEN** the cron does not run during that session, and the next start through the script turns it off
  and records it

#### Scenario: A database that cannot be neutralised

- **WHEN** the script is pointed at a database where the check still finds something that can act after
  re-neutralising
- **THEN** it does not start Odoo, and names what can act
