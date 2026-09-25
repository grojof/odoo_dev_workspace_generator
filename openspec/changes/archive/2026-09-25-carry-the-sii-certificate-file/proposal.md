# Proposal

## Why

Up to 13.0, `l10n_es_aeat_sii` keeps the AEAT certificate (the `.p12`) in a column of its own table: a
binary field is not an attachment by default in 12.0. The 14.0 migration of `l10n_es_aeat_sii_oca`
(`migrations/14.0.1.0.0/pre-migrate.py`) creates one `l10n.es.aeat.certificate` per old record. It copies
name, state, dates and key paths, and moves `ir_attachment` rows only. So the certificate file never
reaches the new model, and the attachments it moves get the old record's id instead of the new one. On
the first client's copy, both certificates arrived without their file, while the file was still in the
old table. The keys are files on the old server's disk, so they have to be obtained again on the new
server in any case. Without the file, that also means asking the client for the `.p12` again.

## What Changes

For a chain whose source is 13.0 or older, the driver's repair after the 14.0 step also carries each
certificate's file from the old table (linked by OpenUpgrade's legacy column) into the new certificate,
through the ORM, when the new one has none. It prints how many it carried, and reminds the operator that
the keys must be obtained again on the new server with the certificate's password. It does nothing when
the tables or the legacy column are absent, or when a certificate already has its file.

## Capabilities

### Modified Capabilities

- `migration-run`: the 14.0 repair also carries the SII certificate file.

## Impact

- `odoo_dwg/templates.py` (the repair script), tests, `tools/verify_migration_driver.py`, docs.
- Upstream: an issue for OCA/l10n-spain may follow; not part of this change.
