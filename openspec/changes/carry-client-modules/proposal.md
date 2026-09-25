# Proposal

## Why

A client's own modules reach the target in one of two ways:
- **Adapted in place.** Each module keeps its name, and its target-version code sits in the target step's
  `custom` directory. The target step's `--update all` migrates it with its own scripts. This already works.
- **Refactored while porting.** The client's modules get a new name, often under a prefix the integrator
  chooses for that client. Several old modules can be folded into one, and some are replaced by an OCA or
  standard module or retired.

The second way is optional, and it is the one the first real client needed: 25 modules from two
integrators, named inconsistently, are being ported into seven area modules under the client's prefix.
The tool has no step for it.
- **Renaming the module record by hand is unsafe.** It has to happen before the new code is loaded, so that
  the module's own migration scripts run with the old data.
- **The order is a trap.** Uninstalling an old module before its replacement is installed deletes the
  tables it shares with the replacement. This was measured on the first client: the old module was the
  only owner of a model whose table holds years of inventory adjustments.

Each rehearsal of the port would also re-run the whole chain (1.5 to 3.5 hours) to test a change in one
module.

Every step of the migration is driven by an assistant through the command line, so the operator declares
the modules' fates, checks them and repeats the stage without the menus.

## What Changes

- **A decision can name the module that carries the old one.** `decisions.json` gains two kinds, both with
  a `to`:
  - `renamed` (`to`: one module): the old module's record, and so its data identifiers, become the new
    module's. Several old modules renamed to the same module are merged into it;
  - `replaced` (`to`: one or more modules): the replacements are installed, then the old module is
    uninstalled.

  `dropped` modules still installed at the target are uninstalled. `kept` and `deferred` mean what they
  meant before. Coverage reads every kind as it reads a decision today.
- **A new stage in the driver, after the target step: the client's modules.** It reads the decisions when it
  runs, so changing them needs no regeneration. In this order:
  1. the operator's `hooks/<target>-modules-pre.sql`;
  2. the renames, with OpenUpgrade's own library (`update_module_names`, merging);
  3. one Odoo run that updates the renamed modules and installs the replacements, so each renamed module's
     `migrations/<target version>/` scripts run on its old data;
  4. the uninstalls, only after everything was installed;
  5. `hooks/<target>-modules-post.sql`, then neutralise, a checkpoint `<target>-modules` and a line in the
     step record.

  With nothing to carry, the stage says so and writes no checkpoint. A module that is not installed is
  skipped and named.
- **The stage can be repeated on its own.** `run_migration.sh <dump> --redo-modules` removes the stage's
  checkpoint and restores the target checkpoint, so only this stage runs again.
- **Two non-interactive commands.**
  - `odoo-dwg migrate modules --source S --target T [--database DB]`: read-only. It prints what the stage
    will do (renames, merges, installs, uninstalls) and what would stop it:
    - a `to` module that does not resolve in the target's sources;
    - a manifest version outside the target series;
    - a renamed module with stored data but no migration scripts, which is a warning.

    With `--database`, it also reads which old modules are installed there and whether a new name is
    already taken. It exits 0 when the stage can run, 1 when something stops it, 2 when it cannot tell.
  - `odoo-dwg migrate decide MODULE --source S --target T --decision KIND [--to M…] [--reason TEXT]`:
    prints the decision it would record, and writes it to the environment's `decisions.json` only with
    `--write`, replacing the module's earlier entry.
- **The command-line rule is widened.** A non-interactive command may write the environment's own operator
  record (`decisions.json`) when asked with `--write`. Host and database changes stay behind the
  interactive confirmation.
- **One source of truth for the stage's plan.** The plan is computed by a standard-library-only module whose
  source the driver embeds verbatim, so the command and the driver cannot disagree.

Out of scope:
- splitting one old module into several new ones. The old module is renamed to the part that owns its data,
  and the other parts take their records in their own migration scripts, which is the module's job;
- the client's prefix or naming rules: the tool carries whatever names the decisions give;
- making the other interactive actions scriptable, such as regenerating an environment, promoting modules
  or neutralising.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `migration-run`: the client-modules stage, its checkpoint and `--redo-modules`.
- `migration-preflight`: the `renamed` and `replaced` decisions, and `migrate modules`.
- `operator-interface`: `migrate decide`, and the rule that lets a command write the operator's record.

## Impact

- **New pure module** `odoo_dwg/carry.py`: the stage plan from the decisions and the target sources. It is
  standard-library only and embedded in the driver.
- **Existing code:**
  - `models.py`: `ModuleDecision.to`, and the decision kinds;
  - `templates.py`: the driver stage and `--redo-modules`;
  - `workflows/checks.py`, `cli.py`, `i18n.py`: the two commands.
- **Tests and verification:**
  - new tests;
  - `tools/verify_migration_driver.py` gains the stage against stub binaries;
  - the stage itself is run on the first client's migrated database (Ubuntu 24.04 under WSL): rename,
    update, install, uninstall, and a `--redo-modules` repeat. The real run is not verifiable from the
    stubs.
- **Docs:**
  - `docs/migration/running.md`, `docs/reference/commands.md`, `README.md`;
  - the `migration-coherence-check` skill is untouched;
  - `CHANGELOG.md`, `docs/project/roadmap.md`.
