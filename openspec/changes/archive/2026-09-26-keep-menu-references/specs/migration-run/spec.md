# Spec Delta

## ADDED Requirements

### Requirement: Rows that reference menus the chain deletes are put back at the target step

At the source restore, the driver SHALL keep every row of each two-column table that references
`ir_ui_menu` through a foreign key, except `ir_ui_menu_group_rel`. Each row SHALL be kept with:
- its menu's external id;
- the table and id of its other side.

After the source configuration and before its checkpoint, the target step SHALL put back each kept row
that is missing. It SHALL find the menu by its external id, or by its id when it has none. For a menu the
chain deleted, it SHALL use the successor declared in `odoo_dwg/menurefs.py`, when that successor exists
in the target.

A row SHALL NOT be put back when:
- its menu has no successor;
- its other side no longer exists;
- its table no longer exists.

Each such row SHALL be listed. Every row put back or left SHALL be listed in
`logs/<target>-menu-references.tsv`. When the source checkpoint holds no kept rows, the step SHALL skip
this, say so, and record it.

#### Scenario: A hidden menu replaced by the chain

- **WHEN** a user had `account.menu_action_invoice_tree1` hidden in the source and the chain replaced it
- **THEN** the user has `account.menu_action_move_out_invoice_type` hidden at the target, and the row is
  listed as restored through a successor

#### Scenario: A deleted menu without a successor

- **WHEN** a kept row's menu is gone and no successor is declared, or the successor is not in the target
- **THEN** nothing is inserted for it, and the row is listed with its menu's external id

#### Scenario: A second run

- **WHEN** the step runs again on the same database
- **THEN** it inserts nothing
