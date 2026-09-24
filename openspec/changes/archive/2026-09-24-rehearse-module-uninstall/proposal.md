# Proposal

## Why

The availability check finds installed OCA modules whose code is missing at some step of the chain. For
those, the first real intake proposed to uninstall them before the chain and reinstall in the target
where the client uses them. OpenUpgrade documents no procedure for this case: its maintainers leave it to
the operator — port the module's scripts, or uninstall it and accept losing its data
(OCA/OpenUpgrade#5336, #394). Uninstalling deletes every record the module owns, drops its tables and
columns with `CASCADE`, and uninstalls every module that depends on it.

So "uninstalling loses nothing" has to be shown on the client's data, not reasoned. The first intake
reasoned it from `ir_model_data` and `ir_model_fields`. That covers what a module owns, but not what a
cascade, a dependent module or an uninstall hook takes with it. Only running the uninstall and comparing
every table shows that.

A second gap surfaced while recording that reasoning: the findings ledger accepted a key it does not know
(`links` on a finding), validated it, and the next write through the tool would have dropped it.

## What Changes

- **Rehearse uninstalling modules** — a new step in **Migration → Take in a client copy**:
  - it takes a neutralised working copy and the modules to uninstall;
  - it clones the copy to a throwaway database and gives it a hard-linked filestore;
  - it uninstalls the modules there, with the source version's own Odoo, then re-neutralises the
    throwaway copy;
  - it compares every table of the two databases, row counts and columns, and names what each
    difference is: the modules' own data (reloaded on reinstall), wizard or metadata rows, a recomputed
    column, or **client data lost**;
  - it records the comparison as a data table and one finding, with the dependents the uninstall took
    along. It refuses the reference, a copy that is not neutralised, and a module that is not installed.
- **The ledger refuses unknown keys** on a finding, so what validates is what the tool keeps.

## Capabilities

### Modified Capabilities

- `client-intake`: the uninstall rehearsal step.
- `migration-findings`: unknown keys on a finding are a validation problem.

## Impact

- `odoo_dwg/intake.py`: the snapshot SQL and the comparison (pure).
- `odoo_dwg/planners.py`: the rehearsal plan (clone, filestore, uninstall, re-neutralise).
- `odoo_dwg/workflows/intake.py`: the step, its refusals, and what it records.
- `odoo_dwg/findings.py`: the unknown-key check.
- `tools/verify_intake.py`: the snapshot and comparison on a throwaway PostgreSQL, and the uninstall
  command against a stub interpreter.
- Docs: `docs/migration.md`, `docs/commands.md`, `CHANGELOG.md`, `docs/roadmap.md`.
