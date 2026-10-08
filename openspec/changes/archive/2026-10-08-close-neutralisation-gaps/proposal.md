# Close the neutralisation catalogue's gaps

## Why

The instance manager, whose catalogue was taken from this one, was checked against the Odoo 14.0–19.0 and OCA
l10n-spain sources. The same gaps are here. A rule that names a column a version lacks is skipped in silence.
The check reads the same rules, so it reports the copy clean:

- **Odoo's Spanish EDI on 14.0–17.0.** It stays in production. The rules name `l10n_es_sii_test_env` and
  `l10n_es_tbai_test_env`, which exist only from 18.0; 14.0–17.0 use `l10n_es_edi_test_env`.
- **The EDI proxy on 14.0–16.0.** Its mode is a parameter (`account_edi_proxy_client.demo`), not the
  `edi_mode` column.
- **Google Calendar tokens on 15.0–17.0.** They live in `google_calendar_credentials`.
- **IAP accounts on 18.0–19.0.** The rule requires `service_name` as a label, and that field is not stored
  there, so the whole rule is skipped.
- **Not covered at all:**
  - VERI\*FACTU, Odoo's (17.0–19.0) and OCA's (`l10n_es_verifactu_oca`);
  - OCA TicketBAI (`l10n_es_ticketbai_api`);
  - the Malaysian and Greek EDI;
  - web push devices and keys;
  - cloud storage;
  - certificate and Twilio passwords.
- **Mail on 12.0–15.0.** A queued mail whose message names a mail server is sent through that server even when
  the mail capture has archived it (`connect()` browses the id without checking `active`; 16.0 refuses).

Odoo's own `neutralize.sql` is not run here. It deletes rows and records nothing, and this neutralisation has
to give production's values back on request. Each gap is closed with a rule that changes a value and records it.

## What changes

- Rules for every gap above, each citing its source.
  - Where Odoo deletes, the rule writes an inert value instead: an empty cloud-storage setting, a push endpoint
    that does not resolve, an empty VAPID key, `dummy` passwords.
  - The values are recorded like every other change, so a restore gives them back.
- A label is only how the check names rows. A table without its label column is still neutralised; the rows
  are then named by id.
- An `Insert` may carry a condition. The EDI proxy parameter is added only on the versions that read it, and
  the check reports it when it is missing.
- The citations of the existing rules are corrected to the versions their columns exist in.

## Impact

- Spec: `copy-neutralisation` (catalogue and severities).
- Code: `odoo_dwg/neutralise.py`.
- Tests: `tests/test_neutralise.py`.
- Tools: `verify_neutralise_sources.py` checks the new citations against the local clones;
  `verify_neutralisation.py` runs the catalogue against a throwaway PostgreSQL.
