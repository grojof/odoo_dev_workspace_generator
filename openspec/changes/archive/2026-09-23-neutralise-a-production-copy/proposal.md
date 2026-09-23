# Proposal

## Why

A copy of a client's production database is armed from the moment Odoo starts on it:
- **every cron fires at once.** Their `nextcall` is in the past by the time the dump reaches us;
- **a tax-reporting module in production mode** needs only one click to submit real invoices to the tax
  agency;
- **the copy identifies itself to Odoo's services as production.** Its IAP tokens and `database.uuid` are
  production's;
- **links point at the production server.**

Mail capture solves one of these paths, reversibly. Everything else is still open. We migrate on a
development host and then open the result there for testing, so a copy must be neutralised before
anything starts it, and must stay neutralised afterwards.

Odoo's own `odoo-bin neutralize` does not fit:
- it exists only from 16.0, and a chain starts from 12;
- it is **one-way**: it replaces `database.secret`, empties IAP tokens and deletes push devices;
- it knows nothing about OCA modules, such as the Spanish SII.

What we need instead: a neutralisation that keeps a record of everything it turned off, inside the
database, like the mail capture. Giving production its settings back must be an **explicit, separate
request**, never something a migration does on its own.

## What Changes

- **An action that neutralises a database, and records every change it makes** in a table inside that
  database: which row, which column, the value before and the value set. The record travels with the
  database through every dump, restore and migration step.
  - It turns off every cron except a declared housekeeping allowlist.
  - It applies the mail capture.
  - It holds pending queue jobs.
  - It takes tax, EDI, payment, delivery, OAuth, calendar and IAP integrations out of production mode.
  - It points `web.base.url` at the local instance and unfreezes it.
  - It gives the copy its own `database.uuid`.
  - It sets `database.is_neutralized`, so 16.0 and later show their own banner.

  Applying it twice is harmless. The second run neutralises only what appeared since the first, for
  example a cron a migration step created.
- **A declared catalogue of rules.** Each rule names the table and columns it touches, applies only where
  they exist, and cites its source:
  - rules derived from Odoo's `data/neutralize.sql` (16.0–19.0), made reversible;
  - rules of our own for OCA modules, starting with the Spanish SII in 12.0 (`l10n_es_aeat_sii`) and
    13.0 onwards (`l10n_es_aeat_sii_oca`).
- **A read-only check**, `odoo-dwg neutralise check --database X`. It reports what in a database can
  still act on the outside and exits non-zero if anything can. It writes nothing.
- **A restore action, behind its own confirmation phrase, only ever on request.** It puts back exactly
  the recorded values. It reports rows that no longer exist. It leaves neutralised what did not exist in
  production, such as crons a migration created, and names them for the operator to decide.
- **The migration driver neutralises** the working database right after restoring the source dump, and
  again after every step, before the checkpoint is taken. It never restores. A migrated database, and
  every checkpoint, is neutralised when it is opened.

Out of scope:
- producing findings from what neutralisation touched (that belongs to the client-intake change, which
  records into the findings ledger);
- network-level blocking, which the outbound firewall already provides and which stays the safety net
  under this.

Verifiable off-host: the catalogue, the rendered SQL, and the plans. The SQL is additionally executed
against a throwaway PostgreSQL by a new verifier. Starting Odoo 12–18 on a neutralised copy and seeing
no cron, mail or tax call leave is a host-side check on the reference box.

## Capabilities

### New Capabilities
- `copy-neutralisation`: covers the following:
  - neutralising a copy of a production database reversibly, with a record kept inside it;
  - the rule catalogue and its sources;
  - the read-only check;
  - the explicit, manual restore.

### Modified Capabilities
- `migration-run`: the driver neutralises the working database after restoring the source dump and after
  every step, before checkpointing, and never restores.

## Impact

- **New code:**
  - `odoo_dwg/neutralise.py`: the catalogue, and the SQL for apply, check and restore;
  - planners and actions reached from the Workspace and Migration menus, beside mail capture;
  - `neutralise check` in `checks.py` and `cli.py`;
  - driver changes in `templates.py`.
- **Reused:** mail capture (`egress.mail_capture_sql` / `mail_restore_sql`), which is composed in, not
  duplicated.
- **Tests:** unit tests for the catalogue, the rendered SQL and the plans.
  `tools/verify_neutralisation.py` runs apply, check, re-apply and restore against a throwaway
  PostgreSQL with tables shaped like 12.0 and 18.0. `tools/verify_migration_driver.py` is extended.
- **Docs:** `docs/migration.md`, `docs/egress-control.md`, `docs/commands.md`, `README.md`, `CHANGELOG.md`
  and `docs/roadmap.md`.
- **No runtime dependency. Nothing AI-related.**
