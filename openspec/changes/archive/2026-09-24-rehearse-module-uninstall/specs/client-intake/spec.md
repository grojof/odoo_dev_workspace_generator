# Spec Delta

## ADDED Requirements

### Requirement: Uninstalling modules is rehearsed on a throwaway copy and compared table by table

The system SHALL offer an intake step that shows, on the client's own data, what uninstalling a set of
modules deletes. It SHALL take:
- a working copy of the reference;
- the modules to uninstall.

It SHALL refuse, before any plan:
- the reference database;
- a copy that is not neutralised (the neutralisation check finds something armed, or the mail can leave);
- a module that is not installed in the copy;
- a throwaway database name that already exists.

Before any plan, the step SHALL name every installed module that depends on those asked for, directly or
not, because the uninstall takes each of them along. The first real intake reasoned from what each module
owned and missed a client module that depended on one of them.

**The rehearsal.** One previewed plan, confirmed with a phrase:
1. The working copy SHALL be cloned to a throwaway database. The working copy itself SHALL NOT be
   modified.
2. The throwaway database SHALL get its own filestore, hard-linked to the reference's, as a copy opened
   for testing does.
3. The modules SHALL be uninstalled there by the source version's own Odoo (the client's core, its
   add-ons, its interpreter), with no HTTP service and no cron thread.
4. The throwaway database SHALL be neutralised again and checked, because an uninstall reloads the
   registry and can write crons.

**The comparison.** Both databases SHALL be read, and for every table of the working copy the step SHALL
record the exact row count before and after, and every column that is gone. Each difference SHALL be named
as one of:
- **module data:** rows the uninstalled modules owned through `ir_model_data`, which a reinstall loads
  again;
- **wizard:** the table of a transient model;
- **metadata:** the registry's own tables (`ir_model*`, `ir_ui_*`, actions, access rules, translations);
- **recomputed:** a dropped column of a related field, filled again by a reinstall;
- **data lost:** anything else — rows beyond what the modules owned, or a dropped column that held values.
  For a dropped column, the number of rows that held a value SHALL be read from the working copy; `false`
  and the empty string are how Odoo stores "unset", and SHALL NOT count as values.

A many2many table named after a transient model's table SHALL count as wizard. The tool's own record
(`odwg_*` tables), which the re-neutralisation writes to, SHALL count as metadata.

The modules the uninstall took along, beyond the ones asked, SHALL be named.

The step SHALL record the comparison as a data table, and one finding: `high` when any client data is
lost, naming the tables and columns; otherwise `info`, stating that no client data was lost and how many
rows of each other kind went. If it cannot read either database, it SHALL say it could not tell, and SHALL
record nothing.

The throwaway database SHALL be left in place for inspection, and the step SHALL say so.

#### Scenario: A module that owns only its own configuration

- **WHEN** the rehearsal uninstalls a module whose only rows are its own export templates
- **THEN** those rows are named module data, and the finding is `info`

#### Scenario: A dropped column that held values

- **WHEN** an uninstalled module's stored, non-related field held values in 3 rows
- **THEN** the column is named data lost with 3 rows, and the finding is `high`

#### Scenario: A dependent module goes too

- **WHEN** an installed module depends, directly or through another, on one asked for
- **THEN** it is named before the plan, and again among the modules the uninstall took along

#### Scenario: A value Odoo stores for "unset"

- **WHEN** a dropped boolean column is `false` on every row
- **THEN** it is named empty, not data lost

#### Scenario: A copy that is not neutralised

- **WHEN** the working copy has an active cron outside housekeeping
- **THEN** the step refuses before any plan, and names the neutralise action
