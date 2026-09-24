# Proposal

## Why

The client's own modules are the part of a migration no source can answer for. Deciding which to drop,
replace or port needs, per module, what it stores, whether anybody still uses it, who depends on it, and
whether its data survives the chain. The first client's audit of 25 modules answered this with one-off
queries. They were the same queries for every module, and they will be the same for the next client. The
audit also showed where the database stops answering. Odoo does not record a print, and that client's
production log was set not to record requests. Only the web proxy's access log says which documents are
printed and how often.

## What Changes

A new step in **Migration → Take in a client copy**, **Audit the client's own modules**. It reads the
reference (read-only) and, for every module the intake classified as the client's own, records:

- **dependents**: the installed modules that depend on it;
- **models it created**: rows, and rows written since a date. For a wizard, how many times it was opened,
  from its id sequence;
- **stored fields it created**: how many rows hold a value (`false` and `''` are not values), how many were
  written since the date, and the last write. A related field is marked recomputed;
- **many2many links** it created: rows;
- **documents it declares** (report actions):
  - whether they are in the Print menu;
  - whether they are registered under another module's namespace, a migration trap;
  - the attachments whose name starts as the document names its PDF;
- **whether OCA publishes a module of that name**, from the intake's cached OCA trees;
- optionally, **in a migrated database**: whether each field and table survived, and with the same count.

Given a web access log (Odoo's, or a proxy's), the step also counts prints per document since the date,
from `/report/<pdf|html>/<document>/` requests.

Each module gets a label from the evidence: *no data*, *not used since <date>*, or *in use*. The decision
stays the operator's. The step records a data table and one finding.

## Capabilities

### Modified Capabilities

- `client-intake`: the audit of the client's own modules.

## Impact

- `odoo_dwg/intake.py`: the SQL builders, the log reader and the labelling (pure).
- `odoo_dwg/workflows/intake.py`: the step.
- Tests, and `tools/verify_intake.py` against a real PostgreSQL.
- `docs/migration.md`, `docs/commands.md`, `CHANGELOG.md`, `docs/roadmap.md`.
