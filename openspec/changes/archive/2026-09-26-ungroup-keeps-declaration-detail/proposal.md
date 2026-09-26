# Proposal

## Why

The repair of grouped invoice items gave an amount to every zero-amount invoice line of a group. Some of those
lines were not inserted by OpenUpgrade 13.0: they were source journal items at zero that it reused as invoice
lines. Such an item can be counted, at zero, in a filed declaration box. After the repair it carried an amount
under other taxes while still linked to that box, so drilling into the box showed a few euros more than was
filed. On the first client, several VAT return boxes were off by a few euros. What was filed did not change;
the detail an auditor would open did. None of the checks looked at that detail.

## What Changes

- **A reused source item keeps its zero.** A zero-amount line whose invoice line OpenUpgrade 13.0 marked as
  matched (`account_invoice_line.aml_matched`) is a source item, not an inserted line. It keeps its zero, its
  taxes and its links, and a group that needed it is left and named.
- **A new check: every record linked to a repaired grouped item adds up to the same.** For each link table,
  the sum of the journal items linked to each such record (a declaration box, a VAT book line) must not
  change. A repair that would change one keeps nothing and stops the run.
- **The analytic accounts OCA `account_financial_report` stores on each line are the line's own**, like its
  taxes and tags: never copied from the grouped item, never a reason to leave a line out.

## Capabilities

### Modified Capabilities

- `migration-run`: the grouped-items repair leaves reused source items as they are, and checks each linked
  record's detail.

## Impact

- `odoo_dwg/ungroup.py`, `tests/test_ungroup.py`, `tools/verify_grouped_invoice_lines.py`.
- Docs: `docs/migration/running.md`, `CHANGELOG.md`.
- Validated on the first client's migrated database: those boxes' detail equals the source's again.
