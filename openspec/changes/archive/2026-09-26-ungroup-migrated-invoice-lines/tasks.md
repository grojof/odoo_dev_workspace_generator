# Tasks

## 1. The repair

- [x] 1.1 `odoo_dwg/ungroup.py` holds the repair's SQL: groups, checks as assertions, links by foreign key,
      the groups left on stdout. `templates.py` runs it in the target step for a source up to 12.0 and a
      target from 16.0. Verified by `tests/test_ungroup.py` and `tests/test_migration.py`: rendered for
      12→18 and 12→16 after the post hook and before the checkpoint, and not for 13→18, 14→18 or 12→15.
- [x] 1.2 `tools/verify_grouped_invoice_lines.py` runs the SQL against a throwaway PostgreSQL. Covers:
      - a grouped invoice and a grouped refund;
      - lines that cancel out, with rounding cents;
      - a zero-amount line with the union of taxes;
      - a group that does not add up, next to one that does;
      - an open item on a reconcilable account, a reconciled item, and a foreign-currency move;
      - an unknown reference;
      - a copied many-to-many link and moved single references;
      - a check forced to fail, which rolls back;
      - a second run that finds nothing;
      - databases without grouped items or without the columns.

      Verified by the tool passing. It caught a two-column detail table being copied as a link.
- [x] 1.3 `tools/verify_migration_driver.py` (a 12→16 chain records the repair before its target's `ok`;
      12→14 does not) and `tools/verify_generated_shell.py`: verified by both tools passing

## 2. Validation and docs

- [x] 2.1 On the first client's migrated 18.0 database, the repair's SQL in a rolled-back transaction.
      Every filed VAT return and EC sales list was recalculated identical before and after. The invoice
      analysis by product matched the source, except for invoices the source already held inconsistently.
      No client data in the repo.
- [x] 2.2 Docs: `docs/migration/running.md`, `CHANGELOG.md`, `docs/project/roadmap.md`,
      `CONTRIBUTING.md` and `AGENTS.md` (the new verifier); verified by `openspec validate` and a grep of
      each claim
