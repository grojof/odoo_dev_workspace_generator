# Proposal

## Why

Odoo up to 12.0 can post an invoice with its lines grouped: one journal item per account and taxes
instead of one per invoice line (the journal's "group invoice lines" option, or a module doing the same).
OpenUpgrade 13.0 builds each invoice's lines from those items. It matches what it can, marks the rest
`exclude_from_invoice_tab`, and inserts the unmatched invoice lines with a zero balance. The amount stays
on the grouped item, and 13.0 to 15.0 hide that item from the invoice.

OpenUpgrade 16.0 fills the new `display_type` without reading `exclude_from_invoice_tab`. So from 16.0
every grouped item is a product line: an extra "/" line on every such invoice, with the whole amount and
no product, while the real lines carry their prices and a zero amount.

The accounts and the tax-based declarations stay right, since the grouped item keeps its account, partner
and taxes. What reads the amount of a product line does not:
- the invoice analysis puts every such sale and purchase under "no product" and counts quantities twice;
- margins by product are wrong;
- every printed or portal invoice shows the extra line;
- a credit note copies the extra line.

On the first client, grouping covered every invoice of several years.

## What Changes

- **After the target step, for a chain from 12.0 or older to 16.0 or later**, the driver moves each grouped
  item's amount to the invoice lines it stands for, and deletes the item. Afterwards each invoice reads
  as if it had never been grouped. This is what Odoo itself does when such an invoice is reset to draft.
- **An amount only moves between lines of the same move, account and taxes.** So every account's balance,
  every partner's balance and every tax's base stay as they were, by construction. Declarations already
  filed (VAT returns, EC sales lists, VAT books) recompute to the same figures.
- **The repair checks itself before it commits.** Every changed move must be balanced. Its amounts must
  be unchanged per account, per account and partner, and per tax, and so must what is still open. Every
  link to a deleted item must have moved. If any check fails, nothing is kept and the run stops.
- **Some items are left grouped, and named.** These are:
  - a group whose amounts do not match its lines;
  - a grouped item already reconciled, partly or fully;
  - an invoice in a foreign currency;
  - an item that something the repair does not know how to move still points at.
- **It runs once, before the target checkpoint.** A resumed run does not repeat it, and a chain that does
  not cross 16.0 from 12.0 does not run it.

Out of scope:
- Detecting leftover grouped items in `migrate audit` (a later change).
- Tag-based tax reports: the migrated lines' tax tags are not touched.
- Foreign-currency invoices.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `migration-run`: a known OpenUpgrade 16.0 defect on grouped invoice items is repaired after the target
  step, when the chain starts at 12.0 or older and reaches 16.0 or later.

## Impact

- `odoo_dwg/templates.py`: the repair's SQL and its place in the target step of the driver.
- `odoo_dwg/i18n.py` if any operator-facing text is added.
- `tests/test_migration.py`: where the repair is rendered and where not.
- New `tools/verify_grouped_invoice_lines.py`: the SQL, run against a throwaway PostgreSQL on synthetic
  12-shaped-then-16-typed invoices.
- `tools/verify_migration_driver.py`: the target step records the repair.
- Docs: `docs/migration/` running page, `CHANGELOG.md`, `docs/project/roadmap.md`, `CONTRIBUTING.md`
  (the new verifier).
- Not verifiable in the unit suite: the SQL itself, which needs PostgreSQL. It was verified against
  PostgreSQL by the new tool, and on the first client's migrated 18.0 database. That validation
  recalculated every filed VAT return and EC sales list before and after the repair, and compared the
  invoice analysis with the 12.0 source.
