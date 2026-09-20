# Design

## What the chain actually does to a module

Harvested from the 2341 `upgrade_analysis.txt` files of OpenUpgrade 14.0 → 19.0 in the environment's own
clones, the field-level changes are, by count:

| Count | Change | Loud or quiet |
|---:|---|---|
| 473 | field removed (`DEL`, 164 plain + 309 relational) | loud — the module will not load |
| 308 | field moved module (`module is now X`, `previously in module X`) | quiet |
| 139 | new field with a default | quiet |
| 43 | `not stored anymore` / `is now stored` | **quiet, and the column goes** |
| 51 | `now a function` / `not a function anymore` | quiet |
| 45 | `not related anymore` / `now related` | quiet |
| 59 | `DEL selection_keys` | quiet — rows keep a key nothing accepts |
| 30 | `needs conversion to v18-style company dependent` | quiet |

and at model level, 240 obsolete models and 779 new ones, plus `apriori.py`'s renamed and merged modules
and models.

The loud half already fails the step, and `verify_migration_driver.py` proves the driver stops on it. The
quiet half is what this change is for.

## A probe is a declaration, not synthesized model code

The tempting design is to make each probe a *reference* — a `many2one` to the model that goes obsolete, a
stored related to the field that stops being stored — so the module breaks the way a client's would. It is
rejected here, for one reason: a synthesized reference that is wrong does not fail at the step it is
testing, it fails to install on the **source** version, and destroys the rehearsal instead of measuring it.
A `related=` path cannot be derived from an analysis line, and generated Odoo model code cannot be verified
against Odoo 12 to 19 from this repository at all.

So a probe is a **declaration**: a row the module installs into its own table, naming the upstream subject,
the class of change, the step the sources predict it at, and the analysis line it came from, verbatim.
Nothing is synthesized that cannot be checked here.

That loses nothing this change is for. The loud classes are already loud — the client's own modules and the
driver catch them. The quiet ones are invisible precisely because no code refers to them, and a declaration
plus a `SELECT` is what makes them visible. After a step, whether the subject
still exists is a question about `ir_model` and `ir_model_fields` — two ordinary tables — so the check is a
`SELECT` against the migrated database, next to the mail check and the coverage reader. Nothing has to be
executed inside Odoo to find out, which also means the answer survives a step where the module failed to
load.

## Why the probes are derived per chain

A fixed module would encode the changes of the chain it was written for. `apriori.py` alone differs by 86
renamed modules between 14.0 and 16.0. The generator reads the environment's own clones — the ones the run
will use — so the probes are the changes *this* migration will meet, and a class with no instance in this
chain produces no probe and is reported as uncovered rather than silently absent.

## What the check can and cannot say

It compares what the analysis predicted against what the database now holds, per step:

- `intact` — the subject is still there and nothing predicted it would go;
- `gone as predicted` — the analysis said it would go at this step, and it did. The chain behaved;
- **`gone unannounced`** — it is not there and nothing predicted it. This is the finding;
- **`still there`** — the analysis said it would go and it did not, so a script did not run;
- `absent` — the tester's own table is missing: the module did not install, which is itself the answer.

It does not say whether the *data* was migrated correctly — no tool can, without knowing what the data
meant. It says whether the structures the analysis talked about ended up where the analysis said.

## Refusals

The generator writes only under a `MigrationEnv`'s own directories, and the manifest carries
`"installable": True` with a summary that says what it is. It declares no menu, no security group and no
access rule beyond its own table, so installing it on a database by accident changes nothing a user sees.
`auto_install` is never set.
