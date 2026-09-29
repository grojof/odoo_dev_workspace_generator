## MODIFIED Requirements

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

OpenUpgrade archives, at every step, each active filter whose domain or grouping no longer loads
(openupgradelib's `disable_invalid_filters`), and nothing reactivates it. At the source restore the driver
SHALL keep which filters were active. After the rewrite, and again at the end of the client-modules stage,
it SHALL reactivate every kept filter the chain archived, then run OpenUpgrade's own check on the active
filters, so a filter still invalid is archived again by the same rule. It SHALL list each filter
reactivated or left archived in `logs/<step>-saved-filters.tsv`. A filter the operator archived in the
source SHALL stay archived.

A filter saved on a window action the chain deleted SHALL first move to the target's action for the same
documents, when `odoo_dwg/savedpaths.py` declares it with its evidence (Odoo 12's invoice actions, one per
invoice type, to Odoo 13's and later move actions for that type); its action is kept by external id at the
source restore. The move SHALL be listed.

#### Scenario: A filter grouping invoices by their 12.0 date

- **WHEN** a filter on `account.move` groups by `date_invoice:month`
- **THEN** it groups by `invoice_date:month`

#### Scenario: A domain value that changed with its field

- **WHEN** a filter's domain has `("account_id.internal_type", "=", "payable")`
- **THEN** it becomes `("account_id.account_type", "=", "liability_payable")`

#### Scenario: A field with no successor

- **WHEN** an export has the column `contracts_count`, which has no successor
- **THEN** the column is dropped and listed, and the rest of the export is kept

#### Scenario: A filter the chain archived and the rewrite repaired

- **WHEN** a filter active in the source groups by `date_invoice:month`, OpenUpgrade archived it at 13.0,
  and the target step rewrote it to `invoice_date:month`
- **THEN** it is active at the target, and listed as reactivated

#### Scenario: A filter still invalid at the target

- **WHEN** a filter active in the source names a field no successor replaces, and the chain archived it
- **THEN** OpenUpgrade's check archives it again, and it is listed as left archived

#### Scenario: A filter saved on an action the chain deleted

- **WHEN** a filter active in the source was saved on Odoo 12's customer invoices action, which the chain
  deletes
- **THEN** it moves to the target's customer invoices action, is reactivated, and both are listed

## ADDED Requirements

### Requirement: The tool's kept tables are dropped when the run completes

The tables the driver keeps at the source restore (`odwg_kept_*`) SHALL stay in the checkpoints, so a
resumed run and `--redo-modules` find them. When the run completes, after the client-modules stage, the
driver SHALL drop them from the working database, and SHALL say so. The neutralisation's own tables SHALL
stay.

#### Scenario: A completed run

- **WHEN** a run completes
- **THEN** the working database has no `odwg_kept_*` table, and the target checkpoint still has them
