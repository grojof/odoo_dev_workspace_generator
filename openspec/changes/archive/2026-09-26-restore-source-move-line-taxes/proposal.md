# Proposal

## Why

OpenUpgrade 13.0 (`account` 13.0.1.1, `migration_invoice_moves`) turns each 12.0 invoice line into a
journal item. Where it can, it reuses the item the invoice had already posted. It then gives every reused
item the taxes of its invoice line, with `INSERT … ON CONFLICT DO NOTHING` into
`account_move_line_account_tax_rel`. So it *adds* them to the taxes the item already had, and never takes
any away.

When an item and its invoice line did not bear the same taxes, the item ends up bearing both sets. This
happens where the source grouped journal items, and on the odd payable line matched by the relaxed
criteria. The amount does not change, but it now counts in the base of every tax it bears.

The OCA AEAT declarations select lines by their taxes. So from 13.0 on, a VAT return or withholding return
recomputed for such a period is wrong. On the first client, 50 journal items were affected:
- withholding and deductible VAT bases were overstated by thousands;
- one intra-EU base was off by a large amount;
- a month not yet filed at the time was among the affected periods.

The source's own taxes exist only in the source. OpenUpgrade keeps no record of what it added.

## What Changes

- **The driver keeps the source's journal-item taxes.** For a source up to 12.0, right after restoring the
  source dump and before its checkpoint, it copies `account_move_line_account_tax_rel` into a table of its
  own. It also records the highest journal-item id the source has.
- **After the 13.0 step**, after its post hook and before neutralising and checkpointing, it takes back from
  each journal item OpenUpgrade reused every tax that:
  - the item did not bear in the source;
  - its invoice line did bear.

  An item is reused when it existed in the source and OpenUpgrade linked it to an invoice line. Nothing else
  is touched: taxes OpenUpgrade or later steps change for other reasons stay as they are.
- **It lists what it took back** in `logs/13.0-taxes-taken-back.tsv`, prints the count, records the repair
  in the step record, and drops its tables. It runs in one transaction.
- **A run without that table skips the repair and says so.** This is the case of a checkpoint taken before
  this change. The only remedy is a run from the source dump.

Out of scope:
- Detecting such items in `migrate audit` (a later change).
- A 13.0 or later source: the taxes are the source's own.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `migration-run`: the source's journal-item taxes are kept at the start of a run from 12.0 or older, and
  the taxes OpenUpgrade 13.0 added to reused journal items are taken back after the 13.0 step.

## Impact

- New `odoo_dwg/sourcetaxes.py`: the SQL that keeps and the SQL that takes back.
- `odoo_dwg/templates.py`: both in the driver, for a source up to 12.0.
- `tests/test_migration.py`, `tests/test_sourcetaxes.py`.
- New `tools/verify_source_taxes.py`: the SQL against a throwaway PostgreSQL, on journal items shaped the
  way OpenUpgrade 13.0 leaves them.
- `tools/verify_migration_driver.py`: the source restore keeps the taxes, and the 13.0 step records the
  repair.
- Docs: `docs/migration/running.md`, `CHANGELOG.md`, `docs/project/roadmap.md`, `CONTRIBUTING.md`,
  `AGENTS.md`.
- Validated on the first client's migrated 18.0 database, by taking back the added taxes (found from the
  source) in a rolled-back transaction:
  - every changed VAT return and withholding return period came back to the figure the source holds;
  - the only exceptions were a few with invoices entered after they were calculated there.
