# Spec Delta

## ADDED Requirements

### Requirement: Saved filters and exports whose fields the chain renamed are rewritten

After the menu references and before its checkpoint, the target step SHALL rewrite saved filters and
export columns that name a field the target lacks, when `odoo_dwg/savedpaths.py` declares a successor
and the target has every field the successor names. It SHALL follow each path through the target's
relations, in domains, groupings, orders, sorts and export columns.

It SHALL NOT:
- change a filter it cannot rewrite whole;
- touch a filter or export whose model is gone.

It SHALL drop an export column that has no successor, and a column that ends up equal to an earlier
one. It SHALL list every change and every record left in `logs/<target>-saved-paths.tsv`.

#### Scenario: A filter grouping invoices by their 12.0 date

- **WHEN** a filter on `account.move` groups by `date_invoice:month`
- **THEN** it groups by `invoice_date:month`

#### Scenario: A domain value that changed with its field

- **WHEN** a filter's domain has `("account_id.internal_type", "=", "payable")`
- **THEN** it becomes `("account_id.account_type", "=", "liability_payable")`

#### Scenario: A field with no successor

- **WHEN** an export has the column `contracts_count`, which has no successor
- **THEN** the column is dropped and listed, and the rest of the export is kept
