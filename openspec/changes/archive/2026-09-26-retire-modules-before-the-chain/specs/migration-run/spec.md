# Spec Delta

## ADDED Requirements

### Requirement: Modules decided dropped before the chain are uninstalled after the source restore

On a fresh run, right after restoring the source dump into the working database and before the database
preflight, the kept taxes and declarations and the source checkpoint, the driver SHALL uninstall every
installed module decided `dropped` with `"when": "before-chain"` for the chain's pair. It SHALL read the
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
