# Design

## Which tables

A table is kept when it has exactly two columns and a foreign key from one of them to `ir_ui_menu`. That
is the shape of an Odoo many2many relation. The table on the other side comes from the other column's
foreign key; a column without one has no other side to check, and the table is skipped and listed.

`ir_ui_menu_group_rel` is left out. It holds the groups Odoo's modules declare on their menus, which each
module update rewrites from its data. Carrying a vanished menu's groups onto its successor would widen or
narrow who sees the successor, against what the module declares.

## Successors

A successor is declared only when both menus open the same documents, with the evidence cited next to it
in `menurefs.py`:

| Deleted menu | Successor | Evidence |
|---|---|---|
| `account.menu_action_invoice_tree1` | `account.menu_action_move_out_invoice_type` | OpenUpgrade 13.0 `account` analysis (DEL/NEW). 12.0 action: `type = out_invoice`; target action: `default_move_type: out_invoice`. |
| `account.menu_action_invoice_out_refund` | `account.menu_action_move_out_refund_type` | same analysis; `out_refund` on both sides |
| `account.menu_action_invoice_tree2` | `account.menu_action_move_in_invoice_type` | same analysis; `in_invoice` on both sides |
| `account.menu_action_invoice_in_refund` | `account.menu_action_move_in_refund_type` | same analysis; `in_refund` on both sides |
| `sale.menu_report_product_all` | `sale.menu_reporting_sales` | OpenUpgrade 16.0 `sale` analysis DEL, 17.0 NEW; the same action `sale.action_order_report_all` |
| `purchase.menu_procurement_management_pending_invoice` | none | OpenUpgrade 13.0 `purchase` analysis DEL; the Purchase app has no bills menu from 13.0 |

Mapping the Purchase app's bills menu to the Invoicing app's bills menu would change what a user sees in
another app, so it is not done: the row is listed as having no successor. A deleted menu without an entry
in this table is listed the same way, so the operator decides.

## Resolving a menu

By external id first, because the chain may delete a menu and create it again with a new id. A menu
without an external id (made from the interface) is found by its id, if it still exists. A successor is
used only when its own external id resolves in the target.

## Putting rows back

The restore is plain SQL: nothing in it needs the ORM. A row is inserted only when:
- its table exists;
- the menu resolves;
- the other side's row exists;
- the pair is not there already.

This makes a second run a no-op. Each row is listed as `restored`, `restored-successor`, `no-successor`,
`other-gone` or `table-gone`. Rows already present are only counted.
