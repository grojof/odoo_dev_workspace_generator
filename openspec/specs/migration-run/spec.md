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

### Requirement: The SII certificate file reaches the new certificate model

For a chain whose source is 13.0 or older, the repair after the 14.0 step SHALL carry the file of every
`l10n_es_aeat_sii` record into the `l10n.es.aeat.certificate` created from it, found through OpenUpgrade's
legacy column, when that certificate has no file. It SHALL write through the ORM, print how many files it
carried and that the keys must be obtained again with the certificate's password, and record the repair in
the step record. It SHALL do nothing when either table or the legacy column is absent.

#### Scenario: A 12.0 copy with a certificate

- **WHEN** the old table holds a certificate with its file and the new certificate has none
- **THEN** the repair writes the file to the new certificate and says the keys must be obtained again

#### Scenario: No SII module

- **WHEN** the database has no `l10n_es_aeat_sii` table
- **THEN** the repair carries nothing and does not fail

### Requirement: The client's modules are carried to their ported names after the chain

A client's own modules may reach the target under new names: renamed, several folded into one, or replaced
by other modules. This is optional; a module adapted under its own name is migrated by the target step as
before.

The driver SHALL run a stage after the target step that reads the environment's decisions when it runs,
and applies them in this order:
1. the operator's `hooks/<target>-modules-pre.sql`, when present;
2. every `renamed` module that is installed, renamed to its `to` module, or merged into it when that module
   already exists;
3. one Odoo run that updates the renamed modules and installs the `replaced` modules' replacements, so that
   each renamed module's own migration scripts run on the old module's data; a `replaced` module retired
   before the chain is not installed any more, and its replacements, itself included, are installed;
4. the uninstall of every `replaced` and `dropped` module still installed, only after step 3 succeeded,
   and never when it would also remove an installed module that no decision drops or replaces;
5. `hooks/<target>-modules-post.sql`, when present.

The stage SHALL run plain Odoo at the target, without OpenUpgrade's framework.

Before touching the database, the stage SHALL refuse to start when a `to` module resolves nowhere in the
target's sources, or when its manifest is unreadable, declares it not installable, or has a version
outside the target series. It SHALL name each refused module. It SHALL uninstall nothing unless every
module it updated or installed is installed afterwards, since Odoo skips a module it cannot load and still
succeeds.

A decided module that is not installed SHALL be skipped and named. A `kept` or `deferred` module still
installed with no code at the target SHALL be named, and left as it is.

When no decision asks for anything, the stage SHALL say so and change nothing. Otherwise the stage SHALL
neutralise the database, write its own checkpoint `<target>-modules`, and record itself in the step record
like a step, with each rename, install and uninstall named, and a failure recorded as the stage's failure.
A resumed run SHALL treat the stage like a step: skipped when its checkpoint exists, and run from the target
checkpoint otherwise. A working database the stage changed without writing its checkpoint SHALL be
replaced by the target checkpoint before the stage decides anything, including that there is nothing to
carry; the run SHALL never end on a database carried half-way.

The driver SHALL accept `--redo-modules`, which removes the stage's checkpoint once the checkpoints are known
to come from the given dump, so the stage alone runs again from the target checkpoint.

#### Scenario: Two old modules folded into one new module

- **WHEN** two installed modules are both decided `renamed` to the same new module, whose code at the
  target holds migration scripts
- **THEN** the stage renames the first, merges the second into it, updates the new module so its scripts
  run on the old data, and records each operation

#### Scenario: A replacement is installed before the old module goes

- **WHEN** a module is decided `replaced` by a module that adopts a table the old one owns
- **THEN** the replacement is installed and only then is the old module uninstalled, so the table survives

#### Scenario: An uninstall that would take another module along

- **WHEN** a module decided `dropped` is a dependency of an installed module that no decision drops
- **THEN** the stage uninstalls nothing, names the module that would have gone with it, and stops

#### Scenario: A decision whose new module is not on disk

- **WHEN** a module is decided `renamed` to a module that resolves in none of the target's sources
- **THEN** the stage stops before changing the database and names the missing module

#### Scenario: Nothing to carry

- **WHEN** the environment's decisions hold no `renamed`, `replaced` or `dropped` entry for an installed
  module
- **THEN** the stage says there is nothing to carry, and writes no checkpoint

#### Scenario: A carry that stopped half-way

- **WHEN** a stage committed its renames, then failed while updating, and the next run's decisions carry
  nothing
- **THEN** that run restores the target checkpoint before saying there is nothing to carry

#### Scenario: Repeating the stage while porting

- **WHEN** the driver is run with `--redo-modules` after a completed run
- **THEN** it restores the target checkpoint and runs only the client-modules stage again

#### Scenario: A module retired before the chain is installed again at the target

- **WHEN** a module is decided `replaced` by itself with `"when": "before-chain"`, and its code is on the
  target's addons path
- **THEN** the driver uninstalls it after the source restore, and the stage installs it at the target, with
  the settings it keeps in core fields as the chain left them

### Requirement: Grouped invoice items become the invoice lines they stand for, after the target step

For a chain whose source is 12.0 or older and whose target is 16.0 or later, the driver SHALL repair the
invoices whose journal items were grouped at the source. It SHALL run right after the target step and its
post hook, and before neutralising and checkpointing.

A grouped item is a journal item of an invoice or credit note that:
- OpenUpgrade 13.0 excluded from the invoice tab;
- is typed as a product line;
- has no invoice line of its own.

The repair SHALL work on each group of one move, one account and one set of taxes. A group is repaired when:
- its grouped items and its zero-amount invoice lines add up to the same amount, in the document's
  direction;
- the move is in its company's currency;
- no grouped item of the group is reconciled, partly or fully;
- nothing points at a grouped item that the repair does not know how to move.

A zero-amount invoice line is one OpenUpgrade 13.0 inserted at a zero amount. A source journal item that
OpenUpgrade 13.0 reused as an invoice line (its invoice line marked as matched) is not one. It SHALL keep its
zero, its taxes and every link it has, because a filed declaration's detail may count it; a group that needed
it is left. A zero-amount invoice line SHALL be keyed on its own source invoice line's taxes when these are
known, and SHALL take them. When the move has a single grouped account and its lines add up to it, the lines SHALL
take that account.

In a repaired group:
- each invoice line SHALL take its own amount, in the document's direction, with the grouped item's
  partner;
- the cents of rounding SHALL go to the group's largest line;
- on a reconcilable account, each line SHALL stay open for its amount, as the grouped item was;
- a many-to-many link to a grouped item SHALL be copied to every line of the group, except the line's own
  attributes (its taxes, its tax tags, its analytic accounts), which each line keeps as its own;
- a known single reference SHALL move to the group's largest line: an analytic line, and an EC sales list
  record or refund detail;
- the grouped items SHALL then be deleted.

Other groups SHALL be left as they are, with the reason for each.

The repair SHALL run in one transaction and commit only if all of these hold:
- every changed move is balanced;
- per move, the balance of each account, of each account and partner, and of the lines bearing each tax is
  unchanged, and so is the amount still open per account and partner;
- the invoices' stored amounts are unchanged;
- no link to a deleted item is lost, and no reference to one either: each analytic line and detail is
  still there;
- every record a repaired grouped item was linked to adds up to the same amount over its linked journal
  items (what a declaration box shows when drilled into).

Otherwise it SHALL keep nothing and stop the run, naming the check that failed. It SHALL print the groups
it repaired and left, record the repair in the step record, and write the groups it left, with the reason,
to a file in the environment's logs. It SHALL do nothing when the database has no grouped items or lacks
the columns it reads.

#### Scenario: A 12.0 → 18.0 chain

- **WHEN** the driver of a 12.0 → 18.0 chain is generated
- **THEN** its 18.0 block repairs the grouped invoice items after the post hook and before the checkpoint,
  and no other step does

#### Scenario: A chain that does not need it

- **WHEN** the driver of a 13.0 → 18.0 or of a 12.0 → 15.0 chain is generated
- **THEN** no step repairs grouped invoice items

#### Scenario: An invoice with two products grouped into one item

- **WHEN** a posted invoice has two invoice lines at zero amount and one grouped item on their account and
  taxes that carries their sum
- **THEN** each invoice line carries its own amount, the grouped item is gone, and the move, its accounts,
  its partners and its taxes add up as before

#### Scenario: Lines that cancel out

- **WHEN** an invoice has a line and its opposite on one account, under different taxes, grouped into one
  item per tax
- **THEN** each line takes its own signed amount from the item with its taxes, and each tax's base is
  unchanged

#### Scenario: A group that does not add up

- **WHEN** a grouped item's amount differs from the sum of the invoice lines on its account and taxes
- **THEN** that group is left grouped, is named with its reason, and the other groups of the move are
  still repaired

#### Scenario: A source item at zero reused as an invoice line

- **WHEN** a source journal item at zero, counted in a declaration box, was reused by OpenUpgrade 13.0 for an
  invoice line with other taxes, and its group needs it to add up
- **THEN** the item keeps its zero, its taxes and its box, the group is left and named, and the box's detail
  adds up as before

#### Scenario: A check that fails

- **WHEN** any of the checks does not hold after the repair
- **THEN** the database is left as the target step left it and the run stops naming the check

#### Scenario: A resumed run

- **WHEN** a run resumes after the target checkpoint
- **THEN** the repair does not run again, since the checkpoint already holds its result

### Requirement: The taxes OpenUpgrade 13.0 adds to a reused journal item are taken back after the 13.0 step

For a chain whose source is 12.0 or older, the driver SHALL keep the source's journal-item taxes. It SHALL do
this right after restoring the source dump into the working database, and before the source checkpoint:
- every row of `account_move_line_account_tax_rel` goes into a table of its own;
- that table holds the highest journal-item id of the source too.

After the 13.0 step, after its post hook and before neutralising and checkpointing, the driver SHALL take
back from each reused journal item every tax that it did not bear in the source and that its invoice line
bore. A reused journal item is one that existed in the source and that OpenUpgrade 13.0 linked to an invoice
line. No other tax of any journal item SHALL be changed.

The repair SHALL:
- run in one transaction;
- write each tax it took back to a file in the environment's logs (journal item, move, tax, amount);
- print how many taxes it took back and from how many items;
- record the repair in the step record;
- drop its tables.

When the kept taxes are absent (a source checkpoint taken without them), it SHALL change nothing and say
that only a run from the source dump can repair it.

#### Scenario: A 12.0 → 18.0 chain

- **WHEN** the driver of a 12.0 → 18.0 chain is generated
- **THEN** its source restore keeps the journal items' taxes before the source checkpoint, and its 13.0
  block takes back the added taxes after the post hook and before the checkpoint

#### Scenario: A 13.0 source

- **WHEN** the driver of a 13.0 → 18.0 chain is generated
- **THEN** it keeps no taxes and no step takes any back

#### Scenario: An item grouped in the source

- **WHEN** a source journal item bore taxes A and B, and OpenUpgrade 13.0 linked it to an invoice line
  bearing A and C, and gave it A, B and C
- **THEN** after the 13.0 step it bears A and B again, and C is listed as taken back

#### Scenario: A tax changed for another reason

- **WHEN** an item bears a tax it did not bear in the source, and its invoice line did not bear that tax
  either
- **THEN** that tax stays

#### Scenario: A checkpoint without the kept taxes

- **WHEN** the run resumes from a source checkpoint taken before the driver kept the taxes
- **THEN** the 13.0 step changes no tax, and says that only a run from the source dump repairs them

### Requirement: Filed declarations keep their boxes through the chain

The driver SHALL copy the source's filed declarations into tables of its own, right after restoring the
source dump and before the source checkpoint:
- every stored box;
- the box's links to journal items;
- the map lines and maps the boxes point at.

At the target, after the post hook and before the grouped-items repair, it SHALL put back every map, map
line, box and link the chain deleted, with the source's ids, casting each column the target still has to the
target's type. It SHALL:
- put back no link to a journal item the chain no longer has, and count such links;
- check that every box the source held exists with its declaration, number and filed amount, and otherwise
  keep nothing and stop the run;
- list each box it put back in a file in the environment's logs, record the repair in the step record, and
  drop its tables.

When the copies are absent (a source checkpoint taken without them), it SHALL change nothing, record the
repair as skipped, and say that only a run from the source dump checks them.

#### Scenario: A map a later module version no longer ships

- **WHEN** a module update in the chain deletes an older map's lines, and with them a filed return's boxes
  and links
- **THEN** at the target the boxes are back with their ids and amounts, their map line and map are back,
  and their links are back to every journal item that still exists

#### Scenario: A box that no longer holds its filed amount

- **WHEN** a box the source held exists at the target with another amount
- **THEN** nothing is put back and the run stops naming the check

#### Scenario: A checkpoint without the copies

- **WHEN** the run resumes from a source checkpoint taken before the driver kept the declarations
- **THEN** nothing is put back, and the step record and output say the check was skipped

### Requirement: Modules decided dropped before the chain are uninstalled after the source restore

On a fresh run, right after restoring the source dump into the working database and before the database
preflight, the kept taxes and declarations and the source checkpoint, the driver SHALL uninstall every
installed module decided `dropped` or `replaced` with `"when": "before-chain"` for the chain's pair. It SHALL read the
decisions when it runs.

Before uninstalling, it SHALL refuse to start, naming them, when an installed module that depends on one of
them is not itself retired. It SHALL uninstall them with the source version's Odoo, as the Apps screen does,
with no HTTP service and no cron thread, and SHALL stop when any of them is still installed afterwards.

It SHALL neutralise the database first, as the intake's rehearsal uninstalls on a neutralised copy. It
SHALL compare the database before and after the uninstall:
- every table's exact row count;
- every column, and the values held, before, by each column of a stored field the retired modules declare
  (`false` and `''` are not values).

It SHALL name each difference by the rules the intake's uninstall rehearsal uses, so what the operator read
there is what the driver judges:
- **metadata**: Odoo's registry (models, fields, data identifiers, views, menus, actions, access and record
  rules, translations, the module list);
- **wizard**: the table of a transient model, or its many2many table;
- **module data**: rows lost no more than the retired modules owned through their data identifiers;
- **empty**: a table or column that held nothing;
- **recomputed**: a stored related column;
- **grew**: a table that gained rows;
- **accepted**: data lost that the decisions file's `accepted_losses` names for the pair, table by table
  and column by column (a table's name does not accept its columns);
- **data lost**: any other table that lost rows or disappeared with rows, and any other column that
  disappeared with values or whose values were not counted.

Any data lost that is not accepted, any module the uninstall removed beyond the retired ones, and any retired
module still installed SHALL stop the run before the source checkpoint, naming each. Every difference SHALL be
written to `logs/00_source-retired.tsv` with its kind, counts and, for an accepted loss, its reason. The
retirement SHALL be recorded in the step record with the modules it uninstalled.

When no decision retires an installed module, it SHALL do nothing and say so.

#### Scenario: Modules with no code at a later step

- **WHEN** the decisions retire three modules before the chain, and the only rows they take with them are
  metadata, a wizard's table, their own records and a column the operator accepted
- **THEN** the modules are uninstalled right after the source restore, the run goes on, and the logs list
  each difference with its kind

#### Scenario: A loss nobody accepted

- **WHEN** retiring a module removes rows of a table that the modules did not own, such as the users of a
  group they defined, and no accepted loss names it
- **THEN** the run stops before the source checkpoint, naming the table and how many rows it lost

#### Scenario: A module that depends on a retired one

- **WHEN** an installed module depends on a module retired before the chain and is not retired itself
- **THEN** the run stops before uninstalling anything, naming the dependent module

### Requirement: Migrated payments are repaired after the target step

When the chain crosses 18.0, the target step SHALL, after its other repairs and before its checkpoint:

- remove each payment-order payment whose journal entry is not its order's, when exactly one other payment
  of the same bank payment line is on the order's own entry, and nothing points at it but its own links;
- give each posted payment that has no journal its payment order's journal, when that journal is a bank,
  cash or credit journal with one method line for the payment's method, without changing its journal entry;
- recompute every posted payment's state and reconciliation flags, then every posted invoice's payment
  status, with the target Odoo's own methods, again until neither changes, and at most five times;
- stop, keeping none of it, when any journal item's account, amount or reconciliation would change;
- list every payment removed, given a journal, or recomputed to another value, every payment left without a
  journal, and every invoice whose payment status changed, in `logs/<target>-payments-repaired.tsv`.

#### Scenario: A remittance whose line an operator's entry repeats

- **WHEN** a bank payment line has a payment on its order's entry and another on a manual entry that repeats
  its reference
- **THEN** the second payment is removed and listed, and no journal item changes

#### Scenario: A payment order posted through a miscellaneous journal

- **WHEN** a posted payment has no journal and its order's journal is a bank journal with a method line for
  its method
- **THEN** the payment gets that journal and method line, and its journal entry keeps its journal and name

#### Scenario: Payments left in process

- **WHEN** posted payments are `in_process` although their lines are reconciled
- **THEN** they are recomputed as Odoo computes them, and the invoices whose status changed are listed

### Requirement: Stock valuation layers are aligned to on-hand quantity and cost after the target step

For a source up to 12.0 and a target from 18.0, the target step SHALL, after the payments repair and before
its checkpoint, run the target's Odoo to add one valuation layer per storable product with periodic
valuation whose layers' quantity or value differs from its stock on hand, as Odoo values it, at its cost.
The layer SHALL carry that difference, the product's cost and the description "Migration: align to on-hand
quantity and cost". For an average-cost product the layer SHALL hold the remaining quantity and value, and
the earlier layers none.

It SHALL leave, and list, products with automated valuation, FIFO or lot valuation. It SHALL keep nothing
when a journal entry would be created, a cost would change, or an adjusted product would not end at on-hand
quantity times cost. It SHALL list every product aligned, with its quantity and value before and after, and
every product left, in `logs/<target>-valuation-aligned.tsv`.

#### Scenario: Layers rebuilt with drift

- **WHEN** a product's layers hold more value than its stock on hand times its cost
- **THEN** a labelled layer brings them to that value, and no journal entry is created

#### Scenario: Automated valuation

- **WHEN** a product's category values it in real time
- **THEN** its layers are left as they are and the product is listed

#### Scenario: A second run

- **WHEN** the alignment runs on a database it already aligned
- **THEN** it adds no layer

### Requirement: Tax grids are refreshed from the chart template after the target step

When the chain crosses 17.0, the target step SHALL, after the valuation alignment and before its checkpoint,
run the target's Odoo to:
- apply the chart template's reload restricted to taxes, setting the repartition lines' tags of every tax
  whose template is unchanged, and leaving any other tax;
- recompute the tax tags of every journal item of an invoice or credit note from repartition lines: a tax
  line from its repartition line, a base line from its taxes' base repartition lines for the document's
  type;
- archive the tax tags no repartition line or journal item uses and no tax report generates.

It SHALL keep nothing when any journal item's amounts, taxes or tag inversion would change. It SHALL list
every repartition line retagged, every tax left, every tag archived, and the number of journal items
regridded and of plain-entry items left, in `logs/<target>-tax-grids.tsv`.

#### Scenario: Unsigned tags from an older chart

- **WHEN** a tax's repartition lines and journal items still carry the unsigned tags of the source's chart
- **THEN** they get the signed tags of the 18 template, and the old tags nothing uses are archived

#### Scenario: A tax with no template

- **WHEN** a tax matches no unchanged template
- **THEN** its tags stay as they are and it is listed

#### Scenario: A second run

- **WHEN** the refresh runs on a database it already refreshed
- **THEN** it retags nothing

### Requirement: Source configuration the chain changes is put back at the target step

For a target from 18.0, the driver SHALL keep, at the source restore:
- every operation type's return type;
- the reconciliation rules, with their external ids;
- each journal's alias name.

After the tax grids and before its checkpoint, the target step SHALL run the target's Odoo to:
- put back each existing operation type's source return type, where that type still exists;
- archive each operation type the chain created that nothing but its warehouse and other created types
  points at;
- compute the default locations of the types that lack them, on the missing field only;
- recreate the source's default invoice-matching rule, when the company has no such rule, with the
  source's values and the field mapping of OpenUpgrade 15.0;
- give each journal's alias its source name.

It SHALL list everything it changed in `logs/<target>-source-configuration.tsv`. When the source checkpoint
holds no kept configuration, it SHALL skip this, say so, and record it.

#### Scenario: Returns redirected by the chain

- **WHEN** a delivery type returned to its own type in the source and the chain pointed it at a new
  "Returns" type
- **THEN** it returns to its source type again, and the unused "Returns" type is archived

#### Scenario: A resumed run from an older checkpoint

- **WHEN** the source checkpoint does not hold the kept configuration
- **THEN** the step warns, records the skip, and changes nothing

### Requirement: Pending installs with no code are cancelled after the target step

When the chain crosses 18.0, the target step SHALL, last before its checkpoint, run the target's Odoo to
cancel the pending install of every module in state "to install" whose code Odoo cannot find on the
step's addons path. It SHALL leave a pending install whose code exists. It SHALL list both in
`logs/<target>-module-states.tsv`.

#### Scenario: An auto-install module whose code is gone

- **WHEN** the chain leaves an auto-install module "to install" and no addons path holds it
- **THEN** its install is cancelled and listed, and the client-modules stage does not meet it

### Requirement: Rows that reference menus the chain deletes are put back at the target step

At the source restore, the driver SHALL keep every row of each two-column table that references
`ir_ui_menu` through a foreign key, except `ir_ui_menu_group_rel`. Each row SHALL be kept with:
- its menu's external id;
- the table and id of its other side.

After the source configuration and before its checkpoint, the target step SHALL put back each kept row
that is missing. It SHALL find the menu by its external id, or by its id when it has none. For a menu the
chain deleted, it SHALL use the successor declared in `odoo_dwg/menurefs.py`, when that successor exists
in the target.

A row SHALL NOT be put back when:
- its menu has no successor;
- its other side no longer exists;
- its table no longer exists.

Each such row SHALL be listed. Every row put back or left SHALL be listed in
`logs/<target>-menu-references.tsv`. When the source checkpoint holds no kept rows, the step SHALL skip
this, say so, and record it.

#### Scenario: A hidden menu replaced by the chain

- **WHEN** a user had `account.menu_action_invoice_tree1` hidden in the source and the chain replaced it
- **THEN** the user has `account.menu_action_move_out_invoice_type` hidden at the target, and the row is
  listed as restored through a successor

#### Scenario: A deleted menu without a successor

- **WHEN** a kept row's menu is gone and no successor is declared, or the successor is not in the target
- **THEN** nothing is inserted for it, and the row is listed with its menu's external id

#### Scenario: A second run

- **WHEN** the step runs again on the same database
- **THEN** it inserts nothing

### Requirement: Saved filters and exports whose fields the chain renamed are rewritten

After the menu references and before its checkpoint, the target step SHALL rewrite saved filters and
export columns that name a field the target lacks, when `odoo_dwg/savedpaths.py` declares a successor
and the target has every field the successor names. It SHALL follow each path through the target's
relations, in domains, groupings, orders, sorts and export columns.

It SHALL NOT:
- change a filter it cannot rewrite whole;
- touch a filter or export whose model is gone.

It SHALL drop an export column that has no successor, and a column that ends up equal to an earlier
one. It SHALL list every change and every record left in `logs/<target>-saved-paths.tsv`.

#### Scenario: A filter grouping invoices by their 12.0 date

- **WHEN** a filter on `account.move` groups by `date_invoice:month`
- **THEN** it groups by `invoice_date:month`

#### Scenario: A domain value that changed with its field

- **WHEN** a filter's domain has `("account_id.internal_type", "=", "payable")`
- **THEN** it becomes `("account_id.account_type", "=", "liability_payable")`

#### Scenario: A field with no successor

- **WHEN** an export has the column `contracts_count`, which has no successor
- **THEN** the column is dropped and listed, and the rest of the export is kept
