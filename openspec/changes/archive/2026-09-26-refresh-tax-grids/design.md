# Design

## Odoo's own reload, restricted

`account.chart.template._pre_reload_data(company, template_data, {'account.tax': ...}, force_create=False)`
decides, per existing tax, whether its template changed:
- amount type;
- amount;
- number of repartition lines.

For an unchanged tax it reduces the template's values to the repartition lines' tags. It turns their
creates into updates of the existing lines, in order, and skips everything else. `_load_data` then writes
them. The tags come from `_get_account_tax`, which maps the template's tag names to the tags the tax
report generated (`_deref_account_tags`).

`_pre_load_data` and `_post_load_data` are not called: they write the company's settings from the
template, which a migrated company already has.

## Journal items

The rule Odoo applies when it computes taxes:
- a tax line takes the tags of its repartition line;
- a line takes the tags of the base repartition lines of its taxes (`tax_ids`) for the document's type:
  `refund` for a credit note, `invoice` otherwise.

Only tax-applicability tags are replaced, and only on invoices and credit notes. A plain entry's lines
get their document type from their balance and the tax's use, which is more than the move says, so they
are left and counted.

## What is archived

A tax tag that no repartition line or journal item uses, and whose name is not `+formula` or `-formula`
of a `tax_tags` report expression. It is archived, not deleted: the source's legacy tables still
reference it.

## The guard

An md5 over every journal item's:
- id and account;
- debit, credit, balance and amount in currency;
- tax base amount;
- tax line and repartition line;
- tag inversion.

Any difference rolls everything back and stops the step.
