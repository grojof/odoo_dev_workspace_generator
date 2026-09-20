# Tasks

## 1. The classes, harvested

- [x] 1.1 `odoo_dwg/analysis.py`: harvest the quiet classes too (moved module, not stored anymore, not
      related anymore, function changes, removed selection keys, company-dependent), keeping the existing
      breaking records unchanged for the staging scan.
- [x] 1.2 Read `apriori.py`'s renamed/merged modules and models.

## 2. The module

- [x] 2.1 `odoo_dwg/tester.py` (new, pure): choose the probes for a chain from the harvested records, one
      per class where the chain has an instance; report the classes with none.
- [x] 2.2 `odoo_dwg/templates.py`: render the module — manifest, model, the probe declarations, security.
- [x] 2.3 `odoo_dwg/planners.py`: `plan_generate_tester`.

## 3. The check

- [x] 3.1 `odoo_dwg/tester.py`: the SQL for `ir_model` / `ir_model_fields` / the witness table, and the pure
      reading of its rows into a per-probe verdict.
- [x] 3.2 `odoo_dwg/workflows/migration.py`: generate, and check, from the migration menu.

## 4. Proof

- [x] 4.1 `tools/verify_migration_tester.py`: generate the module from real analysis records, byte-compile
      every `.py`, parse every XML, and assert the probe set matches the records it was derived from.
- [x] 4.2 Unit tests for the harvest, the choice and the verdicts; mutation-audit each one.

## 5. Documentation

- [x] 5.1 The delta spec; `openspec validate --specs`.
- [x] 5.2 `docs/migration.md`, `docs/commands.md`, `CHANGELOG.md`, `docs/roadmap.md`, `CONTRIBUTING.md`.
