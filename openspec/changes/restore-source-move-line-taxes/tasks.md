# Tasks

## 1. Keep and take back

- [x] 1.1 `odoo_dwg/sourcetaxes.py`: the SQL that keeps the source's journal-item taxes and highest id, and
      the SQL that takes back the added taxes (one transaction, the list on stdout, its tables dropped, a
      skip when they are absent). Verified by `tests/test_sourcetaxes.py`.
- [x] 1.2 `templates.py`: keep in the source restore of a chain from 12.0 or older, before the source
      checkpoint; take back in the 13.0 block after the post hook and before the checkpoint. Verified by
      `tests/test_migration.py`: rendered for 12→18, not for 13→18. The 12→14 and 12→16 chains run in
      the driver verifier (1.4).
- [x] 1.3 `tools/verify_source_taxes.py` runs the SQL against a throwaway PostgreSQL. Covers:
      - a source with grouped items, then OpenUpgrade 13.0's union simulated;
      - an item with an extra tax its invoice line did not bear, which stays;
      - an inserted item, never touched;
      - the list;
      - the tables dropped;
      - a database without the kept taxes, which is skipped.

      Verified by the tool passing.
- [x] 1.4 `tools/verify_migration_driver.py` and `tools/verify_generated_shell.py`: a 12→14 chain keeps
      the taxes and records the repair at 13.0 before its `ok`; verified by both tools passing

## 2. Validation and docs

- [x] 2.1 On the first client's migrated 18.0 database, the taken-back taxes found from the source in a
      rolled-back transaction: the VAT and withholding returns recalculated before and after, and compared
      with the source's. No client data in the repo.
- [x] 2.2 Docs: `docs/migration/running.md`, `CHANGELOG.md`, `docs/project/roadmap.md`, `CONTRIBUTING.md`,
      `AGENTS.md`; verified by `openspec validate` and a grep of each claim
