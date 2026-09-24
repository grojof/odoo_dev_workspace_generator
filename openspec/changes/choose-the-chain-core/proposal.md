# Proposal

## Why

From 14.0 on, each migration step runs OpenUpgrade on a separate Odoo clone, and the tool always cloned
`odoo/odoo`. A client that runs OCB (OCA/OCB) was therefore migrated onto a different core than the one it
runs. That matters in one place above all. Every step installs the modules whose `auto_install`
dependencies are met, and OCB turns `auto_install` off for a list of modules. The list grows with the
version (four at 14.0, seventeen at 17.0 and 18.0): `iap`, `sms`, `partner_autocomplete`, `mail_bot`,
`base_import_module`, `account_edi_ubl_cii` and others. The first client runs OCB, and its rehearsal on
official Odoo ended with modules installed that it never had, `base_import_module` among them.

The choice is cheap to change afterwards, since OCB is the same code with the same module versions and the
same schema. But what a migration auto-installs stays installed. So the migration is the moment the choice
counts.

## What Changes

- A migration environment has a **chain core**, `odoo` or `ocb`, for the steps that run on a separate
  clone (14.0 and later). By default it follows the core the intake identified. It is `odoo` when there is
  no intake or the core is patched or unidentified. The operator may set it at generation.
- The clones, `addons_path`, `odoo-bin`, requirements and coverage of those steps use the chosen core's
  clone, `.repos/<core>-<version>`.
- A later action reads the choice back from the generated step configs, as it already reads the linked OCA
  repositories. The choice is recorded nowhere else.
- Generation says which core the steps use and why.

Out of scope: steps up to 13.0, which run OpenUpgrade's own full fork of Odoo, and the source clone, which
the intake already pins to the client's core.

## Capabilities

### Modified Capabilities

- `migration-environment`: which core the steps from 14.0 run on.

## Impact

- `odoo_dwg/models.py`: `CORE_FLAVOURS`, `MigrationEnv.chain_core`, the step clone path.
- `odoo_dwg/intake.py`: `FLAVOURS` becomes the models' table.
- `odoo_dwg/planners.py`: the clone plan clones the chosen core.
- `odoo_dwg/workflows/migration.py`: the question at generation, reading the choice back.
- Tests; `docs/migration.md`, `docs/workspace-layout.md` if it names the clones, `CHANGELOG.md`,
  `docs/roadmap.md`.
- Verifiable only on a real host: a whole chain on OCB (the first client's second rehearsal).
