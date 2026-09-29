## MODIFIED Requirements

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
