# Tasks

## 1. The repair

- [x] 1.1 `payments.py`: the duplicates and journals SQL with its checks and listing; the recompute script;
      `applies()`; tests in `tests/test_payments.py`.
- [x] 1.2 `templates.py`: the repair at the target step, after the grouped items; tests.
- [x] 1.3 `tools/verify_migrated_payments.py` against a throwaway PostgreSQL; `verify_migration_driver.py`,
      `verify_generated_shell.py`.

## 2. Validation and docs

- [x] 2.1 The first client's migrated database: counts, the invoices listed, no journal item changed.
- [x] 2.2 Docs: `docs/migration/running.md`, `CHANGELOG.md`, `docs/project/roadmap.md`, `CONTRIBUTING.md`,
      `AGENTS.md`.
