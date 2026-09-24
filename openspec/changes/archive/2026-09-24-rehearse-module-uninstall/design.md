# Design

## Context

The uninstall of an Odoo module (`ir.module.module.module_uninstall` →
`ir.model.data._module_data_uninstall`) deletes the records the module owns, then drops its models' tables
and its fields' columns with `CASCADE`, and uninstalls the modules that depend on it
(`odoo/addons/base/models/ir_model.py`, `ir_module.py` in 12.0). What it removes from the client's data is
therefore the union of three things:
- what the module owned;
- what the cascades reached;
- what its dependents owned.

Only the first can be read beforehand.

## Decisions

**A throwaway clone of the working copy, not the working copy.** The comparison needs the "before" state to
stay queryable: a dropped column's values can only be counted where the column still exists. `createdb -T`
of a 5 GB database takes seconds, and the working copy stays usable for the next rehearsal with a
different set of modules.

**Exact counts, not `reltuples`.** The statistics estimate is refreshed by `ANALYZE`, not by the uninstall's
deletes. One statement per database counts every table through `query_to_xml`, so a table needs no
generated SQL of its own and a name never reaches the shell.

**Classification by ownership, from the before database.** The modules' own rows are counted per model in
`ir_model_data` of the working copy, the model mapped to its table by `_table`'s default (dots to
underscores). A table whose lost rows do not exceed the owned rows lost only module data. More lost than
owned is data lost, whatever the table. That is conservative: a model with a custom `_table` is never
excused.

**Related columns are recomputed; any other dropped column that held values is data lost.** `ir_model_fields`
records `related` for every field in 12.0 and later. A stored computed field that is not related is
counted as data lost, because the tool cannot tell whether the reinstalled module computes it again from
the same inputs.

**The uninstall runs through `odoo-bin shell`, with the script on standard input.** Every supported version
reads a script from a non-terminal stdin. `button_immediate_uninstall` is the same call the Apps screen
makes, so the rehearsal uninstalls exactly as an operator would. The module names are validated against
the manifest-name pattern and passed as a Python literal (`repr`), never interpolated into the shell.

**Re-neutralise after, and check.** The uninstall reloads the registry. The throwaway copy gets the same
neutralisation as any copy before it is left in place.

**Metadata names are declared.** They are `ir_model`, `ir_model_data`, `ir_model_fields`, `ir_model_fields_selection`,
`ir_model_constraint`, `ir_model_relation`, `ir_model_access`, `ir_ui_view`, `ir_ui_menu`, `ir_act_*`,
`ir_translation`, `ir_rule` and `ir_module_*`. Other `ir_*` tables (attachments, crons, parameters,
sequences, properties) are client configuration or data, and are classified like any other table.

**Lessons from the first real run.** The first comparison on a client copy named every stock
move as data lost. They held a boolean that was `false` on every row, which is Odoo's "unset". It also
named a wizard's many2many table and the tool's own neutralisation record as client data. All three are
now classified. The same run found the one real loss: the uninstall took along a client module that
depended on one of the modules asked for. The static reasoning done before the run had missed it. The
step now names the dependents before the plan.

## Risks

- **A long uninstall.** The uninstall of a large module on a large database takes minutes. The plan streams
  Odoo's log, and nothing else waits on it.
- **An uninstall that fails.** Odoo rolls it back, the plan stops at that step, and the throwaway database
  is left as it is, with the failure in the output. Nothing is recorded.
