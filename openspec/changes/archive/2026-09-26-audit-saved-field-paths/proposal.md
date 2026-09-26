# Proposal

## Why

Users' saved filters and export lists cross the chain as records, and none is lost. But the field names
inside them are not rewritten, in three cases:
- Odoo rebuilt a model: the invoices of `account.invoice` became `account.move`, and a filter moved with
  them still names `date_invoice` and `number`.
- A field was renamed through a path: OpenUpgrade's `rename_fields` rewrites a field named directly on the
  filter's or export's model, but not one inside a path such as `picking_ids/picking_supplier_id/...`.
- A module that defined a field was retired.

Odoo then fails on the filter or export when a user opens it. On the first client's migrated database, a
large share of the saved filters and exports named a field the target lacks.

## What Changes

A new `migrate audit` check, `saved-field-paths`, lists every saved filter and export column that names a
field or model the database lacks. It reads each path segment by segment through relations, from:
- a filter's domain, its context's groupings and order, and its sort;
- an export's columns.

A domain is parsed, not evaluated, so a saved `context_today()` does not stop it. Examples carry ids,
model names and field paths only, never a filter's label.

## Capabilities

### Modified Capabilities

- `migration-audit`: saved filters and exports naming fields the database lacks are found.

## Impact

- `odoo_dwg/audit.py`, `odoo_dwg/workflows/checks.py`, `odoo_dwg/i18n.py`;
  `tests/test_migration_audit.py`; `tools/verify_migration_audit.py`.
- Docs: `docs/migration/checks-findings.md`, `docs/reference/commands.md`, `CHANGELOG.md`,
  `docs/project/roadmap.md`.
