## ADDED Requirements

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
   each renamed module's own migration scripts run on the old module's data;
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
