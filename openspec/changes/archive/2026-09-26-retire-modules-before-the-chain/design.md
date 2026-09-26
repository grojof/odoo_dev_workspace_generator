# Design

## Where

On a fresh run, after `pg_restore` of the source dump and before `preflight_db`: the database preflight
checks coverage against the modules installed, and a retired module must be gone by then. It also runs
before the source's taxes and declarations are kept, so those copies describe the source the chain actually
starts from. It runs only when `00_source` has no checkpoint; a resumed run starts from that checkpoint,
which already holds the result.

## How the decisions reach the driver

The driver embeds `carry.py` already, to read the decisions at run time. The same file gains
`retirement(entries, losses, source, target, installed, depends)`. It returns the modules to retire and
the accepted losses, and names what would stop it. The problems it names:
- a malformed name;
- a `when` other than `before-chain`;
- an installed dependent module that is not retired.

Its output is a JSON plan, like the client-modules stage's.

## The guard

The intake's uninstall rehearsal already names every difference an uninstall makes: metadata, wizard,
module data (rows the modules owned through their data identifiers), empty, recomputed (a stored related
column), grew, data lost. The guard uses the same rules, so what the operator read in the rehearsal is what
the driver judges. They move from `intake.py` to a new `odoo_dwg/retire.py`, standard library only, which the
driver embeds verbatim as it does `carry.py`; `intake.py` and the rehearsal's `uninstall_script` take them
from there.

1. **Neutralise**: the rehearsal uninstalls on a neutralised copy, and so does the driver.
2. **Before**, into files under `logs/00_source-retire/`: every base table's exact row count, every column,
   the installed modules, the transient models, the stored related fields, the rows the modules own through
   `ir_model_data`, and the values (not `false`, not `''`) of every column of a stored field the modules
   declare. Counting every column of a large database would take minutes; a column that disappears from a
   table that stays can only belong to a field the uninstall removed, and those fields are known before it.
   A gone column that was not counted is data lost: nothing says it was empty.
3. **The uninstall**: the source version's `odoo-bin shell` runs the rehearsal's own script, the names coming
   from the environment instead of the text.
4. **After**: the row counts, columns and installed modules again; `retire.py compare` classifies, marks as
   `accepted` each data loss the decisions file names (a table's name accepts its rows, not its columns),
   writes `logs/00_source-retired.tsv`, prints every change that is not the registry's, and exits non-zero on
   data lost not accepted, on a module taken along, or on a retired module still installed.

`res_groups_users_rel` is not metadata: it says which user may do what. Losing it is data, and it must be
accepted, like on the first client (the users of a retired option's group).

## Why not replay the rehearsal

The rehearsal runs on a clone of a neutralised working copy, and a fresh dump of production at the cutover
holds other rows. Comparing against the rehearsal's recorded counts would stop every run with a newer dump.
The guard instead checks the real uninstall against rules the operator fixed after reading the rehearsal:
what kinds of rows may go, and which named losses are accepted.
