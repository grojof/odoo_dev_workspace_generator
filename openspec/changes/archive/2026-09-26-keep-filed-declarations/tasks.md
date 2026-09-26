# Tasks

## 1. Keep and put back

- [x] 1.1 `odoo_dwg/declarations.py`: keeping (boxes, links, the maps and map lines they use) and putting back
      (parents first, same ids, cast columns, the check, the list, the tables dropped, a skip without them).
      Verified by `tests/test_declarations.py`.
- [x] 1.2 `templates.py`: keeping at the source restore, putting back at the target before the grouped-items
      repair. Verified by `tests/test_migration.py`.
- [x] 1.3 `tools/verify_filed_declarations.py`: a later module version's deletion simulated (map lines,
      cascading boxes and links), a journal item gone and a column made translatable; a box changed by hand
      stops it; skipped without the copies; nothing kept from a source without declarations. Verified by the
      tool passing.
- [x] 1.4 `tools/verify_migration_driver.py` and `tools/verify_generated_shell.py`: the target records the
      repair before the grouped items; verified by both tools passing.

## 2. Validation and docs

- [x] 2.1 On the first client's migrated database, with the copies built from the source, rolled back: the
      lost returns' boxes put back, the source's number of boxes reached.
- [x] 2.2 Docs: `docs/migration/running.md`, `CHANGELOG.md`, `docs/project/roadmap.md`, `CONTRIBUTING.md`,
      `AGENTS.md`; verified by `openspec validate`.
