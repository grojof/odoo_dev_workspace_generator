# Tasks

## 1. Pure logic

- [x] 1.1 The snapshot SQL (exact row counts and columns per table) and its parser; verify with row-reading
      tests and on a throwaway PostgreSQL
- [x] 1.2 `diff_uninstall` classifying every difference (module data, wizard, metadata, recomputed, data
      lost) and naming the modules taken along; verify each class, a dropped column with values, and a
      table losing more than it owned
- [x] 1.3 The ledger refuses a finding key it does not know; verify the refusal names it

## 2. Plan and step

- [x] 2.1 `plan_uninstall_rehearsal`: clone, filestore, uninstall through `odoo-bin shell`, re-neutralise
      and check; verify the plan in tests, and the uninstall command against a stub interpreter in
      `tools/verify_intake.py`
- [x] 2.2 The intake step: its refusals, the plan, the comparison and what it records

## 3. Real run and docs

- [x] 3.1 Rehearse the first client's group B uninstall on its neutralised copy before committing
- [x] 3.2 `docs/migration.md`, `docs/commands.md`, `CHANGELOG.md`, `docs/roadmap.md`
