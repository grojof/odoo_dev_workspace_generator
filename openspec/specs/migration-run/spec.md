# migration-run Specification

## Purpose

Runs the chain one version at a time against a copy of the source database, checkpointing after each step so a failure is resumable, and never touching production data.

## Requirements

### Requirement: Sequential chain with no skipped versions

The system SHALL compute the migration chain as every version from the one after the source up to the target,
in ascending order, and run each step in that order — never skipping a version (per official OpenUpgrade).

#### Scenario: A 13 → 18 migration runs each intermediate step

- **WHEN** the chain is computed for source 13.0 and target 18.0
- **THEN** the ordered steps upgrade to 14.0, 15.0, 16.0, 17.0, then 18.0, with no gaps

### Requirement: Start from a copy of the source, never production

The `run_migration.sh` driver SHALL begin by restoring a supplied source database dump into a working database
on the shared migration cluster and checkpointing that initial state, and MUST NOT operate on the original
production database.

#### Scenario: Source is restored into a working DB and checkpointed

- **WHEN** the driver starts with a source dump
- **THEN** it creates a working database, restores the dump into it, and writes an initial checkpoint before any step runs

### Requirement: The working database is the environment's own, and is recreated on every restore

The driver SHALL operate on a working database named for its own chain
(`migration_<source major>_to_<target major>`) unless the environment names one explicitly, so two
environments running side by side can neither use nor destroy each other's database. A name given
explicitly MUST be a valid PostgreSQL database name before it reaches the script.

Every restore — of the source dump or of a checkpoint — SHALL drop that database and create it again
before restoring into it: `pg_restore` onto a populated database would merge two states. The environment's
documentation SHALL name the database the driver destroys, because the driver itself asks for no
confirmation: the only thing between an operator and a lost database is that name not being theirs.

#### Scenario: Two chains do not share a database

- **WHEN** a 12 → 15 environment and a 15 → 18 environment are generated under the same base directory
- **THEN** their drivers name different working databases, so neither can drop the other's

#### Scenario: A resume replaces the database rather than restoring onto it

- **WHEN** the driver resumes from the 16.0 checkpoint
- **THEN** it drops and creates the working database again before restoring that checkpoint into it

### Requirement: The run records what it did, step by step

The driver SHALL append one line per event to a step log in the environment's logs directory: when it
happened, which run it belongs to, which step, what happened — started, succeeded, failed, was skipped as
already checkpointed, or restored — and, for a failure, the code the step exited with.

It SHALL be **appended and never rewritten**, so a run interrupted mid-step still leaves a readable record,
and SHALL accumulate across runs: the file is the history of every attempt on that chain.

A failure's recorded code SHALL be the step's own. Reading it from inside a negated test yields the status of
*not having failed*, which is zero, and every failure was recorded as a success.

Each line's timestamp SHALL be in a form the system journal's time filters accept, so a step's window can be
handed to the outbound firewall's journal rather than guessed at — that is how an operator finds out what a
step reached for while it ran.

#### Scenario: A failed step is recorded with the code it failed with

- **WHEN** a step exits non-zero
- **THEN** the step log holds its start and then its failure with that exit code, and no run-completed event

#### Scenario: An interrupted run still leaves a record

- **WHEN** a run is killed while a step is running
- **THEN** the step log holds every event up to that step's start

#### Scenario: A step's window can be asked of the journal

- **WHEN** an operator has a step's start and end from the step log
- **THEN** they are accepted by the journal's time filters as they are written

### Requirement: A run can be followed while it happens

The driver is started by hand and may take hours. The system SHALL offer an action that follows a run from
what the driver writes as it goes, and that only **reads**: where the chain is, what the running step is
saying, and what it has reached for outside its own machine since that step began.

It SHALL show every step of the chain, including those the run has not reached — what has not happened yet
is part of knowing where a chain is — with each step's state and how long it took, or has been taking.

Stopping the watch SHALL NOT touch the run: the driver is another process, and the action SHALL say so on
leaving. It SHALL return to the migration menu rather than abandoning the section, since stopping a watch is
not abandoning the migration.

When the run ends, the action SHALL say how it ended and SHALL point at the report, because the live view
follows the *running* step and its last frame therefore holds no step detail.

Where nothing has been recorded yet, it SHALL say so rather than present an empty chain as an idle one.

#### Scenario: A chain in progress

- **WHEN** a run is on its third step of seven
- **THEN** the first two are shown with the time they took, the third as running with its elapsed time, and
  the remaining four as pending

#### Scenario: Stopping the watch leaves the run alone

- **WHEN** the operator interrupts the watch
- **THEN** it says the driver is unaffected and returns to the migration menu

#### Scenario: The run ends while being watched

- **WHEN** the run records its outcome
- **THEN** the watch reports it and names the report as where the detail is

### Requirement: The runs can be reported on, and what is open is named first

The system SHALL offer an action that reads back what the runs left — the driver's step log, each step's
Odoo log, and the outbound firewall's journal — and writes a report into the environment.

The report SHALL open with **what is still unresolved**, which is what it exists for: a step that failed, a
step that never finished, a step of the chain that never ran, and a step that *passed while its log holds an
error*, since a step succeeding and a step's log being clean are not the same thing. A report with nothing
recorded SHALL say so rather than read as a clean one.

A step's log SHALL be summarised by what its lines carry — level, logger, message and how many times it
occurred — and SHALL NOT be classified by meaning: what an OpenUpgrade step warns about is not something
this project asserts without evidence. Repeated lines SHALL be counted rather than repeated, because one
broken field can emit the same warning per record and ten thousand copies of it hide everything else.

The firewall's answers SHALL be asked for by **the step's own window**, from the step log, and SHALL be
limited to the step's own process, so the report says what the migration reached for rather than what the
host did while it ran. Refusals SHALL come first: on a host with the outbound firewall, Odoo is rejected
anywhere but localhost, so a refusal is the half worth reading. Where the journal cannot be read the report
SHALL say the answers were unavailable rather than imply there were none.

A step reported as skipped SHALL be shown as having run nothing that time, so its silence is not read as a
clean run.

#### Scenario: What is open comes before what happened

- **WHEN** a run's last step failed
- **THEN** the report names it under "still open" before the per-run detail

#### Scenario: A step that passed with errors in its log

- **WHEN** a step exits zero and its log holds an ERROR line
- **THEN** the report names it as open, with the first such message

#### Scenario: A step's reach is asked for by its own window

- **WHEN** a step ran between two recorded instants
- **THEN** the firewall's journal is asked for exactly that window, and only that step's process

### Requirement: Per-branch odoo-bin command shape

The system SHALL run each step with the target version's `odoo-bin` from that step's virtualenv, using
`--update all --stop-after-init`, and SHALL shape the command to that branch's OpenUpgrade layout.

For Odoo ≥ 14 the command SHALL load `base,web,openupgrade_framework` and point `--upgrade-path` at
`openupgrade_scripts/scripts`.

For Odoo ≤ 13 the migration scripts live inside each add-on (`addons/<module>/migrations/<version>/`) rather
than under an upgrade path, and there is no `openupgrade_framework` module to load. That step SHALL therefore
run the OpenUpgrade fork's own `odoo-bin` with **an explicit add-ons path naming the fork's `addons`
directory** (alongside the environment's per-version custom and OCA directories), and without
`--upgrade-path` or `--load`. The add-ons path MUST NOT be left to a default or to an environment's own
configuration: a path that resolves to some other copy of Odoo's add-ons silently skips every non-core
migration script while the step still reports success.

#### Scenario: A modern step loads openupgrade_framework

- **WHEN** the step upgrading to Odoo 18 is emitted
- **THEN** its command includes `--update all --stop-after-init` and `--load=base,web,openupgrade_framework` with `--upgrade-path` set to the OpenUpgrade 18.0 scripts

#### Scenario: The 13.0 step runs the fork's add-ons explicitly

- **WHEN** the step upgrading to Odoo 13 is emitted
- **THEN** its command runs the OpenUpgrade 13.0 checkout's `odoo-bin` from that step's virtualenv with a
  config whose `addons_path` names the checkout's own `addons` directory, and includes neither
  `--upgrade-path` nor `--load`

#### Scenario: An add-on's own migration script runs

- **WHEN** the Odoo 13 step migrates a database with the `iap` module installed
- **THEN** that add-on's `migrations/13.0.1.0` scripts run, so `company_id` is renamed to its legacy name and
  its data moved into `company_ids`, rather than the column surviving unmigrated

### Requirement: A step verifies its own code is on disk

Before running a step the driver SHALL check that the OpenUpgrade code that step needs is present — the
scripts directory and `openupgrade_framework` for 14.0 and later, the fork's `addons` for 13.0 and earlier —
and SHALL abort naming the missing directory. Odoo neither fails nor warns when `--upgrade-path` names a
directory that is not there: it finds no scripts, and the step would be checkpointed as migrated.

A step that fails SHALL abort naming the step and the log file holding the reason, rather than ending the
run with no explanation.

#### Scenario: A missing OpenUpgrade checkout stops the step

- **WHEN** the OpenUpgrade scripts for a step are absent from the shared cache
- **THEN** the driver exits non-zero naming that directory, writes no checkpoint for the step, and does not
  report the migration complete

#### Scenario: A failing step says where to look

- **WHEN** a step's `odoo-bin` exits non-zero
- **THEN** the driver exits non-zero naming the step and its log file

### Requirement: Checkpoint after each step and resume on failure

The driver SHALL `pg_dump` the working database after each successful step and, on a failed step, stop and
leave the last good checkpoint intact so a re-run resumes from it rather than restarting from the source.

On a re-run the driver SHALL restore the newest checkpoint into the working database before the first
pending step. A failed step can leave the database half-migrated, because OpenUpgrade commits module by
module, and that state must never be migrated again.

The driver SHALL record the SHA-256 of the source dump with the first checkpoint, and SHALL refuse to resume
with a different dump. A checkpoint that cannot be written SHALL abort the run naming the step: a chain that
kept going would have no recovery point at all while reporting that it had one. A checkpoint SHALL become visible only once it is complete, so an interrupted
`pg_dump` never leaves a truncated file that a later run would restore.

A run that starts from the source rather than resuming SHALL discard the checkpoints already present, so a
previous chain's dumps are never mistaken for this one's. A resume SHALL restore the newest checkpoint that
is contiguous with the chain: if the checkpoint for a step is missing while a later one exists, the driver
SHALL resume from the last unbroken point rather than skipping the gap.

#### Scenario: Re-run resumes from the last good checkpoint

- **WHEN** step 5 of a chain fails after steps 1–4 succeeded
- **THEN** checkpoints for steps 1–4 remain and re-running the driver resumes at step 5, not at the source

#### Scenario: The half-migrated database is replaced before resuming

- **WHEN** step 16.0 failed after checkpoints for the source and 15.0 were written
- **THEN** the re-run restores the 15.0 checkpoint into the working database and only then runs step 16.0

#### Scenario: A checkpoint that cannot be written stops the chain

- **WHEN** `pg_dump` fails while checkpointing a step
- **THEN** the driver exits non-zero naming that checkpoint, runs no further step, and leaves no
  half-written file behind

#### Scenario: A fresh run discards earlier checkpoints

- **WHEN** the driver is started from the source with checkpoints from a previous chain still on disk
- **THEN** those checkpoints are removed before the source is restored, so no later step can resume onto them

#### Scenario: A gap in the checkpoints is not skipped

- **WHEN** the checkpoints for the source and 16.0 exist but the one for 15.0 does not
- **THEN** the driver resumes from the source and re-runs 15.0, rather than restoring 16.0 and continuing

#### Scenario: An interrupted checkpoint is not resumed from

- **WHEN** a `pg_dump` is interrupted while writing a step's checkpoint
- **THEN** no checkpoint file for that step exists afterwards, and the re-run resumes from the previous one

#### Scenario: A different source dump is refused

- **WHEN** the driver is re-run with a dump whose SHA-256 differs from the one its checkpoints came from
- **THEN** it stops before touching the database and says the checkpoints belong to another dump

### Requirement: Driver preflight before touching the database

`run_migration.sh` SHALL run the host-scope preflight (chain tools, PostgreSQL, dump integrity) before
restoring anything, and the database-scope preflight (source-version match from `ir_module_module`,
installed modules, per-step addons coverage) immediately after the initial restore and before step 1. Any
failed check SHALL abort the driver with a non-zero exit and a message naming the failed check; coverage
findings SHALL name the directory the operator must fill.

#### Scenario: Host failure aborts before restore

- **WHEN** the driver starts on a host where `uv` is missing
- **THEN** it exits non-zero naming the failed check, without creating or restoring the working database

#### Scenario: Version mismatch aborts after restore, before step 1

- **WHEN** the restored database's `base` version does not match the environment's declared source
- **THEN** the driver exits non-zero naming the mismatch and runs no migration step

### Requirement: The driver honours what the operator decided

A module that resolves nowhere and has no successor is the operator's to answer for, and the answer is
recorded. That record SHALL be read by the **driver**, not only by the preflight action, from a known file
in the environment (`decisions.json` at its root). Without it an operator could record a decision, watch the preflight accept it, and
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

The migration environment SHALL include a script that starts Odoo on a chosen database of that
environment. The version SHALL be the chain's **source** version or one of its steps. The database SHALL
be either:
- a copy of the client's reference;
- the working database;
- a database restored from a checkpoint.

Opening any of them for testing SHALL go through this script, which on every start:

1. **Re-neutralises** the database, which covers what an install, update or migration step switched back
   on since the last start.
2. **Runs the check.** If anything can still act on the outside, it refuses to start, naming what can act.
3. **Starts Odoo with cron threads at zero**, listening on loopback only, with the version's add-ons and
   the mail sent to the local capture. A cron that a module installed during this session creates, or
   switches on, cannot run until the next start neutralises it.

For the source version, the script SHALL use the source's own clone, virtualenv and configuration, which
come from the intake when there is one. It SHALL use the environment's data directory, so that an unpacked
client filestore is found.

The script SHALL NOT restore production settings, and SHALL offer no option that skips the
re-neutralisation or the check. It SHALL refuse the reference database itself, which nothing modifies.

#### Scenario: A module installed while testing

- **WHEN** the operator installs a module from the interface of a migrated database opened through the
  script, and that module creates an active cron
- **THEN** the cron does not run during that session, and the next start through the script turns it off
  and records it

#### Scenario: A database that cannot be neutralised

- **WHEN** the script is pointed at a database where the check still finds something that can act after
  re-neutralising
- **THEN** it does not start Odoo, and names what can act

#### Scenario: The client's source instance

- **WHEN** the script is run with the source version on a neutralised copy of the client's reference
- **THEN** it starts the source Odoo the intake identified, with the client's add-ons, with no cron thread

#### Scenario: The reference is refused

- **WHEN** the script is pointed at the reference database
- **THEN** it refuses to start, saying that the reference is never modified and a copy should be opened
  instead

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
