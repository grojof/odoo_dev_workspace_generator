# Tasks

## 1. The catalogue and its SQL (pure)

- [x] 1.1 `odoo_dwg/neutralise.py`: `Rule`, the catalogue (crons + allowlist, queued jobs, Spanish SII of
      Odoo and OCA, TicketBAI, EDI proxy, payment provider/acquirer, delivery, OAuth, calendars, webhooks,
      IAP, mail templates' server, website domain/CDN, `web.base.url`/freeze, `database.uuid`,
      `database.is_neutralized`), each with its source; verify with a test that every rule has a source,
      every allowlisted cron an xmlid and a reason
- [x] 1.2 Apply SQL: record tables, one guarded `DO` block per rule (not-applicable recorded, record before
      write, no overwrite of an existing record, insert kind); verify with rendering tests and the
      idempotence rule
- [x] 1.3 Check SQL (read-only, one row per rule with what can still act) and restore SQL (run-1 records
      written back via `jsonb_populate_record`, inserts deleted, later-run records named, missing rows and
      columns reported); verify with rendering tests, including that the check SQL contains no write
- [x] 1.4 `tools/verify_neutralisation.py`: apply → check → re-apply after adding a cron → restore, against a
      throwaway PostgreSQL with tables shaped like 12.0 (`payment_acquirer`, `sii_*`) and 18.0
      (`payment_provider`, `l10n_es_sii_test_env`); verify it passes and fails when a rule is broken

## 2. Surface

- [x] 2.1 Planners `plan_neutralise` / `plan_restore_production` composing the mail capture's SQL in the
      stated order; verify the plans' order and quoting
- [x] 2.2 Menu actions in Workspace and Migration beside mail capture (phrases `NEUTRALISE`,
      `RESTORE PRODUCTION`; local URL asked with the environment's default); verify with workflow tests
- [x] 2.3 `odoo-dwg neutralise check --database X` in `checks.py`/`cli.py`, reporting per rule plus the
      mail verdict, exit 0/1/2; verify with CLI tests over a stubbed row reader
- [x] 2.4 Operator strings in `i18n`; verify the catalog test

## 3. The driver

- [x] 3.1 Generation writes `neutralise.sql`; the driver runs it after the source restore, after each
      successful step before `pg_dump`, and after a checkpoint restore, stopping on failure, warning when
      the file is absent, never restoring; verify with `tools/verify_migration_driver.py` (stub `psql`
      records the calls and their order) and `tools/verify_generated_shell.py`

- [x] 3.2 Generation writes `open_for_testing.sh <version> <database>`: re-neutralise, check (refuse to start
      on anything armed), then `odoo-bin` of that version with `max_cron_threads = 0`, loopback HTTP,
      the step's addons path and mail to the capture; no skip option, no restore; verify with the
      migration-driver verifier (stub `psql`/`odoo-bin`: refused when the check reports, started with
      cron threads 0 otherwise) and ShellCheck — never by starting a real Odoo

## 4. Sources

- [x] 4.1 `tools/verify_neutralise_sources.py`: every official `data/neutralize.sql` 16.0–19.0 with the rules
      that cite it or `not covered`, every cited table/column found in its file, OCA citations grepped in
      the cached trees; verify it runs clean on the reference host

## 5. Docs and gates

- [x] 5.1 `docs/egress-control.md` (neutralisation beside mail capture), `docs/migration.md` (the driver
      neutralises; restore is manual and when), `docs/commands.md`, `README.md`, `CHANGELOG.md`,
      `docs/roadmap.md`, CONTRIBUTING/CLAUDE verifier lists; verify every command shown runs as documented
- [x] 5.2 Gates: `pytest`, `ruff`, `openspec validate --specs`, `--help`, all offline verifiers; and a
      `git grep` of the tree for any client name, host or real figure before committing

## 6. On the host

- [x] 6.1 Neutralise a copy of the client's reference database (never the reference itself), run the
      check, simulate a module update and a migration-created cron, re-apply, restore and compare every
      touched table's fingerprint; record the outcome in that environment's findings ledger (outside the
      repository). Starting Odoo on the copy with the firewall and Mailpit on is tracked in the roadmap's
      host validation, pending their installation on the reference host
