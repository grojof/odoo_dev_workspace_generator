# Tasks

- [x] 1.1 `grouptaxes.py`: `applies()`, `repair_sql()`; tests.
- [x] 1.2 `templates.py`: the repair after the taxes taken back, before the 13.0 checkpoint; tests.
- [x] 1.3 `tools/verify_group_tax_accounts.py`, on a throwaway PostgreSQL.
- [x] 1.4 Run on a clean 12.0 database with `l10n_es` migrated by stock OpenUpgrade 13.0: the lines written
      equal those of OpenUpgrade with the upstream fix.
- [x] 2.1 The first client: a full run from its original copy with stock OpenUpgrade 13.0; the 15 taxes
      get 472 and 477 on 60 lines, a new bill posts on them, every other repair and comparison as before.
- [x] 2.2 Docs: `docs/migration/running.md`, `CONTRIBUTING.md`, `AGENTS.md`, `CHANGELOG.md`.
