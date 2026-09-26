# Proposal

## Why

Modules outside Odoo's core can point at menus through many2many tables. For example, a module that hides
menus from some users or groups stores a row per user or group and menu. When the chain deletes a menu,
PostgreSQL deletes every such row with it (`ON DELETE CASCADE`), and nothing says so.

OpenUpgrade deletes menus Odoo replaced:
- 13.0 deletes the four invoice menus of `account` and creates the `account.move` ones;
- 16.0 deletes `sale.menu_report_product_all`, and 17.0 creates `sale.menu_reporting_sales` on the same
  action;
- 13.0 deletes the vendor bills menu of `purchase`, which has no successor in the Purchase app.

On the first client's database, one user's hidden customer invoices and credit notes came back visible
after the chain. The same user still had other menus hidden, and nobody would have noticed.

## What Changes

For every chain:
- **At the source restore**, the driver keeps every row of each many2many table that references
  `ir_ui_menu`, except Odoo's own `ir_ui_menu_group_rel`. Each row is kept with its menu's external id
  and the table and id on its other side.
- **At the target step**, after the source configuration, the driver puts back every kept row that is
  missing. The menu is found by its external id, or through a successor for the menus the chain replaced.
  A row is not put back when its menu has no successor, its other side is gone, or its table is gone;
  each such row is listed.
- Everything goes to `logs/<target>-menu-references.tsv`. Without the kept table, the step skips this and
  says so.

## Capabilities

### Modified Capabilities

- `migration-run`: the chain keeps menu references at the restore and puts them back at the target.

## Impact

- New `odoo_dwg/menurefs.py`; `odoo_dwg/templates.py`; tests in `tests/test_menurefs.py`; verifier
  `tools/verify_menu_references.py`.
- Docs: `docs/migration/running.md`, `CHANGELOG.md`, `docs/project/roadmap.md`, `CONTRIBUTING.md`,
  `AGENTS.md`.
