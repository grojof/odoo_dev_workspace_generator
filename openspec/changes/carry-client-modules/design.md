# Design

## Where the stage sits

The stage runs **after** the target step, not inside it. The target step runs OpenUpgrade with `--update
all`: the old names are installed with no code, so it skips them, and the new names are not installed yet,
so it ignores them. After it:
- the database is a clean target-version database;
- the client's old modules are still installed, codeless, with their tables and data identifiers intact.

That is exactly what a rename needs. Keeping the stage out of the OpenUpgrade run has two other benefits:
- a failing port never fails the chain;
- the stage can be repeated from the target checkpoint.

The stage runs plain Odoo: no `--upgrade-path`, no `openupgrade_framework`. The client's modules migrate
with their own scripts, as they would in production.

## The order inside the stage, and why

1. **Pre hook.** The operator's SQL, for anything client-specific the modules' scripts cannot do.
2. **Renames:** `openupgradelib.openupgrade.update_module_names(cr, pairs, merge_modules=True)`, run from
   the target's `odoo-bin shell` with the target venv, which already holds `openupgradelib` because
   OpenUpgrade requires it. `merge_modules=True` folds several old modules into one new name: data
   identifiers, the module record and its dependencies. The renamed record keeps its old `latest_version`
   (for example 12.0.1.0.0), which is below the new module's 18.0.x. So the update in step 3 runs the new
   module's `migrations/18.0.x/pre-migration.py` and `post-migration.py` on the old data, which is where
   field renames (`openupgrade.rename_fields`) belong.
3. **One Odoo run:** `-u <renamed targets> -i <replacements> --stop-after-init`. A single run lets a
   renamed module depend on a replacement, and the reverse.
4. **Uninstalls** of the `replaced` and `dropped` modules still installed, through
   `button_immediate_uninstall()`. Odoo also uninstalls every module that depends on them, so the stage first
   reads their `downstream_dependencies()` and stops if one of them is not itself decided `dropped` or
   `replaced`. They come last because an old module can be the only owner of a model a
   replacement adopts: the first client's `custom_pnt` holds the only `ir.model` identifier for
   `stock.inventory`, whose table OCA's `stock_inventory` takes over. Uninstalling first drops the table.
5. **Post hook, neutralise, checkpoint.**

Everything is re-derived at run time from `decisions.json`. Nothing about the decisions is baked into the
driver, so editing them needs no regeneration, the same as the coverage helper today.

## One plan, computed once

The driver cannot import `odoo_dwg`: it is a standalone script, and the chain venvs do not hold the tool.
The coverage helper today keeps an embedded copy of the preflight's logic, and a requirement had to be
written because the two drifted ("The preflight and the driver answer coverage the same way").

This time the plan lives in one standard-library-only module, `odoo_dwg/carry.py`. Its functions take plain
data: decision dicts, and a `read(name)` callable that finds a module in the target's sources and parses
its manifest. The driver embeds the module's source text, read
through `importlib.resources` when the driver is rendered, and calls the same function the command calls.
A test asserts that the embedded text is the module's.

The plan:
- `renames: list[(old, new)]`, grouped by `new`;
- `updates: list[new]`;
- `installs: list[module]`;
- `uninstalls: list[module]`;
- `problems: list[(module, kind, detail)]`, with kind `blocking` or `warning`.

## Decision kinds

`ModuleDecision.decision` stays free text, so older files keep reading. The recognised kinds are:

| Kind | `to` | Coverage | Client-modules stage |
|---|---|---|---|
| `kept`, `deferred` | none | settles a missing module | nothing, and names it if still installed with no code |
| `dropped` | none | settles | uninstalled if still installed |
| `renamed` | one module | settles | renamed, merged if several share `to`, then updated |
| `replaced` | one or more | settles | `to` installed, then the old module uninstalled |

- `to` is a string for `renamed`, and a string or a list for `replaced`.
- A `renamed` or `replaced` entry without `to`, or a `to` on any other kind, is reported by `migrate
  modules` as blocking, and the stage stops before touching the database.
- An unknown kind is reported and ignored by the stage.
- **`dropped` gains an effect.** Before this change it only settled coverage; now the stage uninstalls a
  `dropped` module still installed at the target. That is what dropping meant, and until now it was done by
  hand after the chain. An existing decisions file gets this effect on the next run of a regenerated
  driver, so `migrate modules` should be read first: it lists every uninstall.

## Checks before touching the database

The stage refuses to start when any of these is true:
- a `to` does not resolve in the target sources (custom first, then OCA and core, the same order as the
  addons path);
- its manifest's `version` does not start with the target series;
- its manifest does not parse, or says `installable: False`.

The plan is computed once, against the database: a decided module the database does not have is only
skipped, whatever its `to`. Odoo exits 0 after skipping a module it cannot load, so the uninstall script
first checks that every module the plan updated or installed is installed, and uninstalls nothing
otherwise.

A rename onto a module already installed merges into it, keeping its version: its `migrations/` scripts do
not run for the merged data, and `migrate modules` warns about it.

A renamed module whose target has no `migrations/` directory is a warning, not a block: some renames need
no data change. `migrate modules` reports the same, and adds what only a database can tell:
- which old modules are installed, and which are not (nothing to carry);
- a `to` that is already installed, which the rename merges into.

## `--redo-modules`

`run_migration.sh <dump> --redo-modules` removes `checkpoints/<target>-modules.dump`, once the
checkpoints are known to be that dump's. The loop for porting: edit a module, redo, look.

**Which database the stage starts from.** Only the target checkpoint can be trusted. The working database
is exactly that when the target step ran in this run. Otherwise the stage looks for
`checkpoints/<target>-modules.dirty`. The stage creates that marker just before it first changes the
database and removes it once its own checkpoint is written, and `--redo-modules` creates it when it
removes a checkpoint. If the marker is there, the stage restores the target checkpoint before deciding
anything, including that there is nothing to carry. A carry that failed half-way is therefore never left
as the result. Without the marker, the working database is the target checkpoint's, and a run with nothing
to carry costs no restore.

## `migrate decide`

- It reads the environment from `--source` and `--target`, as `findings` does, and refuses a pair with no
  environment on disk.
- It refuses a decisions file that exists but cannot be read, instead of taking it for empty.
- It writes the file where it really is, so a link to a shared file stays a link, and keeps its mode.
- It builds the entry with `evidence: {"checked": <today>, "recorded_by": "migrate decide"}`, prints it,
  and with `--write` replaces any entry for the same module and pair.
- The file is written through a temporary file and a rename.
- It never changes another entry and never reorders the file.
- It validates the kind and `to`, as the plan does.

## Rejected alternatives

- **Install the new modules fresh and copy the data across in their init hooks.** A fresh install runs no
  migration scripts. Each module would have to rediscover the old tables, the identifiers would be
  duplicated, then deleted with the old module, and saved filters and exports that name the old fields
  would be lost. Renaming is what OpenUpgrade itself does for renamed modules.
- **Rename inside the target step (as a pre hook).** This couples the port to the OpenUpgrade run: a
  failing port costs the whole target step, and it cannot be repeated alone.
- **A separate `module-map.json`.** The fate of a module is already a decision, keyed by module and pair.
  A second file would restate it.
