# Tasks

## 1. The filters

- [x] 1.1 `savedpaths.py`: `KEPT_ACTIVE`, `keep_sql()`, `ACTION_SUCCESSORS`, `REACTIVATE`; tests.
- [x] 1.2 `templates.py`: keep at the source restore; reactivate after the target rewrite and at the end of
      the modules stage; drop the kept tables when the run completes; tests.

## 2. Validation and docs

- [x] 2.1 The first client: on the migrated database, every filter the chain archived is active again
      (those on a deleted invoice action moved to its successor), and no kept table is left.
- [x] 2.2 Docs: `docs/migration/running.md`, `CHANGELOG.md`.
