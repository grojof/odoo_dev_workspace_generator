# Spec Delta

## ADDED Requirements

### Requirement: The SII certificate file reaches the new certificate model

For a chain whose source is 13.0 or older, the repair after the 14.0 step SHALL carry the file of every
`l10n_es_aeat_sii` record into the `l10n.es.aeat.certificate` created from it, found through OpenUpgrade's
legacy column, when that certificate has no file. It SHALL write through the ORM, print how many files it
carried and that the keys must be obtained again with the certificate's password, and record the repair in
the step record. It SHALL do nothing when either table or the legacy column is absent.

#### Scenario: A 12.0 copy with a certificate

- **WHEN** the old table holds a certificate with its file and the new certificate has none
- **THEN** the repair writes the file to the new certificate and says the keys must be obtained again

#### Scenario: No SII module

- **WHEN** the database has no `l10n_es_aeat_sii` table
- **THEN** the repair carries nothing and does not fail
