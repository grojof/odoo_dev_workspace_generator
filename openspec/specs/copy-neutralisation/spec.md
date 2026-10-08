# copy-neutralisation Specification

## Purpose
Keep a copy of a production database from acting on the outside world while it is migrated and tested — crons, tax and EDI submissions, payments, deliveries, Odoo's online services, mail — with a record, kept inside the database, of everything turned off, and give production its settings back only when the operator explicitly asks.

## Requirements

### Requirement: A copy is neutralised with a record of every change

The system SHALL offer an action that neutralises a chosen database. For every value it changes, it SHALL
record the following in a table inside that database, before changing it:
- the rule;
- the table;
- the row, by id and, where one exists, by its external identifier;
- the column;
- the value it had;
- the value set;
- when.

The record SHALL survive `pg_dump`/`pg_restore` and every step of a migration chain, as the mail capture's
record does.

Neutralising SHALL delete nothing and SHALL leave no value unrecorded. Odoo's own `neutralize` deletes push
devices and replaces secrets irreversibly. This action SHALL instead change a value only where it can put
the original back.

It SHALL apply the mail capture as part of neutralising, through the mail capture's own action and record,
not a second mechanism.

A database named by the operator MUST be a valid PostgreSQL database name before any command is built with
it.

#### Scenario: A production copy is neutralised

- **WHEN** a copy whose crons are active, whose tax integration is in production mode and whose
  `web.base.url` is the production URL is neutralised
- **THEN** its crons outside the housekeeping allowlist are inactive, the tax integration is in test mode
  and disabled, `web.base.url` points at the local instance and is not frozen, and every one of those
  changes is in the record with its original value

#### Scenario: Neutralising twice

- **WHEN** a neutralised database is neutralised again after a migration step has created a new active
  cron
- **THEN** the new cron is turned off and recorded, and no earlier record is overwritten, so the original
  production values are still the ones recorded first

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

### Requirement: Whether a copy can act on the outside is answerable without changing it

The system SHALL offer a read-only check that reports, for a chosen database, everything in it that can
still act on the outside:
- active crons outside the allowlist;
- queued jobs a runner would execute;
- tax, EDI, payment and delivery integrations in production mode;
- enabled OAuth providers and calendar synchronisation;
- enabled webhooks;
- enabled IAP accounts;
- whether mail can leave;
- a `web.base.url` that is not local.

It SHALL state a verdict. It SHALL issue no statement that writes. It SHALL be available as
`odoo-dwg neutralise check --database X`, exiting zero when nothing can act, non-zero when something can,
and 2 when it could not tell.

#### Scenario: A fresh copy of production

- **WHEN** the check is run on a restored production dump that was never neutralised
- **THEN** it lists what can act, exits non-zero, and names the menu action that neutralises it

#### Scenario: A neutralised copy

- **WHEN** the check is run on a neutralised database
- **THEN** it says nothing can act and exits zero

### Requirement: Neutralisation is re-applied, never trusted to last

Neutralisation SHALL be treated as undone by any module install, update or migration step, because Odoo
undoes it on its own:
- updating a module rewrites every cron its data files do not mark `noupdate`, including an `active` value
  the file declares. In Odoo 12.0, 31 of 31 core cron records are updatable. In 18.0, 85 of 93 are.
- installing a module, or reinstalling one, creates its crons active.
- OpenUpgrade loads each step's `noupdate_changes.xml` into records that are otherwise protected.

Re-applying SHALL be cheap and safe: it turns off what came back or appeared, and records only what is new.
Every path the tool offers for starting Odoo on a copy SHALL re-apply it first, as the next requirements
state for the migration environment.

#### Scenario: A module update switches a cron back on

- **WHEN** a neutralised database has a module updated, and that module's data file declares its cron
  `active`
- **THEN** the next neutralisation turns that cron off again, keeps its first record, and the check reports
  nothing can act

### Requirement: Production settings come back only when explicitly asked

The system SHALL offer an action that restores a neutralised database's recorded values. It SHALL run
**only when the operator chooses it and types its confirmation phrase**. No migration step, driver, seed,
workspace action or other flow SHALL call it.

It SHALL:
- put back exactly the recorded original values;
- restore the mail capture through the mail capture's own restore;
- remove its record once everything it names has been dealt with.

It SHALL report, and SHALL NOT restore:
- rows the record names that no longer exist;
- columns that no longer exist.

A row that did not exist in production SHALL be left as neutralised and named, for the operator to decide.
This covers a cron created by a migration step, and any row first recorded after the source database's
first neutralisation.

Where no neutralisation is recorded, the action SHALL say so and change nothing.

#### Scenario: A migrated database opened for testing stays neutralised

- **WHEN** a migration chain finishes and the resulting database is opened on the development host
- **THEN** it is still neutralised, and nothing restored it

#### Scenario: The day of the cutover

- **WHEN** the operator restores the migrated database and types the phrase
- **THEN** the production crons are active again with the state they had, the tax integration is back in
  production mode, `web.base.url` and `database.uuid` are production's, mail flows through the client's
  own servers, and the crons the migration created are listed as left off

#### Scenario: Nothing recorded

- **WHEN** restore is run on a database that was never neutralised
- **THEN** it reports that no neutralisation is recorded and changes nothing

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
