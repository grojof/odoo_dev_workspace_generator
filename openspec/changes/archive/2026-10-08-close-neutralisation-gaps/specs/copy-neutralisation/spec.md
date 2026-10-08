## MODIFIED Requirements

### Requirement: What is turned off is a declared catalogue with its sources

Neutralisation SHALL apply a catalogue of rules declared in the tool. Each rule SHALL name the tables and
columns it reads and writes, and the source it derives from. The sources are:
- an Odoo `data/neutralize.sql`, with the versions it appears in;
- an OCA module, with its repository, branch and file.

A rule SHALL apply only where its tables and the columns it reads and writes exist in the database at hand,
so that one catalogue serves every version from 12.0 to 19.0. A rule that does not apply SHALL be reported as
not applicable, not as done. The column a rule names its rows by is not one of them: a table without it is
still neutralised, and its rows are named by id. Where Odoo's own neutralisation deletes a row or a value, a
rule SHALL write an inert value instead, recorded like every other change, so that a restore gives it back.

The catalogue SHALL cover at least:

| Area | What is turned off or switched to test |
|---|---|
| Crons | Every cron except a declared allowlist of housekeeping crons, each allowlisted by external identifier with the reason it is safe |
| Mail | Through the mail capture; on 12.0–15.0 the mail server a queued mail's message names is cleared, since those versions send through it even when archived |
| Queued jobs | Held so that no job runner executes them |
| Tax and EDI | Odoo's Spanish EDI test environment (`l10n_es_edi_test_env`, 14.0–17.0), its SII and TicketBAI test environments (18.0–19.0) and VERI\*FACTU's (17.0–19.0); the OCA Spanish SII disabled and in test mode, for `l10n_es_aeat_sii` (12.0) and `l10n_es_aeat_sii_oca` (13.0 onwards); OCA VERI\*FACTU and TicketBAI in test mode; the EDI proxy out of production (its `edi_mode`, or on 14.0–16.0 its `account_edi_proxy_client.demo` parameter), the Malaysian and Greek EDI included |
| Payment | Providers or acquirers out of production state |
| Delivery | Carriers out of production environment |
| Accounts and calendars | OAuth providers disabled; Google and Microsoft calendar synchronisation stopped, in every table their tokens lived in from 12.0 to 19.0 |
| Webhooks | Webhook server actions disabled |
| IAP | Accounts disabled; a token longer than 33 characters replaced whole, as Odoo 17.0–19.0 do |
| Push, storage, secrets | Web push keys emptied and devices' endpoints pointed nowhere; cloud storage settings emptied; certificate, private key and Twilio passwords replaced |
| Identity | `web.base.url` pointed at the local instance and unfrozen; a new `database.uuid`; `database.is_neutralized` set |

#### Scenario: One catalogue across versions

- **WHEN** a 12.0 database, which has `payment_acquirer` and no `payment_provider`, is neutralised
- **THEN** the payment rule applies to `payment_acquirer`, and the rules for tables 12.0 does not have are
  reported as not applicable

#### Scenario: The OCA SII after the module was renamed

- **WHEN** a database migrated to 18.0, where the SII module is `l10n_es_aeat_sii_oca`, is neutralised
- **THEN** its companies' `sii_enabled` is false and `sii_test` true, as in 12.0 under `l10n_es_aeat_sii`

#### Scenario: Odoo's Spanish EDI on 14.0–17.0

- **WHEN** a 16.0 database whose companies have `l10n_es_edi_test_env` false is neutralised
- **THEN** it is true afterwards, recorded, and the check no longer reports it

#### Scenario: A rule whose label is not stored

- **WHEN** an 18.0 database has IAP accounts (whose `service_name` is not a stored column)
- **THEN** the IAP rule still applies, and the check names the rows by id

### Requirement: Each rule declares how serious what it guards is

Every rule of the neutralisation catalogue SHALL declare a severity: `critical`, `high`, `medium`, `low` or
`info`. The severity is how much harm the thing the rule turns off could do from a copy. Whatever reports
what a copy can act on SHALL rank it by that severity, and SHALL NOT invent its own.

The declared severities are:

| Severity | Rules |
|---|---|
| **critical** | Tax and EDI submissions, and payment providers in production mode |
| **high** | Crons, queued jobs, delivery carriers, webhooks, OAuth and calendar synchronisation, push devices, cloud storage, certificate and SMS secrets, a queued mail's named server |
| **medium** | IAP accounts, mail templates bound to a server, the base URL and website domain, web push keys |
| **low** or **info** | Identity flags, such as the `database.is_neutralized` banner or the uuid |

#### Scenario: A survey of a production copy

- **WHEN** a copy has an active cron and a tax integration in production mode
- **THEN** the tax integration's finding is critical and the cron's is high, as the catalogue declares
