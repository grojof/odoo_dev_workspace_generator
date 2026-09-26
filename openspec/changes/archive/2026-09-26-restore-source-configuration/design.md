# Design

## What the chain created

A type with an id above every source type's id and a warehouse. It is archived when no foreign key points
at it, except its warehouse's own fields and other created types. That check runs after the return types
are put back, so a delivery type no longer points at a created "Returns". A created type something already
uses stays active and is listed. The warehouse keeps its links to the archived types: clearing them would
make Odoo create new ones at the next warehouse change.

## Default locations

`add_to_compute` of `default_location_src_id` or `default_location_dest_id`, only on the types where that
field is empty, then a flush. This is Odoo's own compute:
- an incoming type gets the vendors' location;
- an outgoing type gets the customers' location.

## The rule

Only the rule whose external id is `account.reconciliation_model_default_rule` is recreated, and only when
the company has no invoice-matching rule. It takes the source's values, with the renames and the
`100 - param` inversion of OpenUpgrade 15.0's `account/15.0.1.2/pre-migration.py`. Auto-validation stays
as the source had it.

## Aliases

Written through `mail.alias`, which sanitises and checks uniqueness. The listing shows the name before and
after.
