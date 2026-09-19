## ADDED Requirements

### Requirement: Optional Mailpit installation

`provision apply` SHALL offer, as an opt-in step, to install Mailpit from a pinned upstream release verified
by its SHA-256 digest. It SHALL run as a system service bound to `127.0.0.1`, with SMTP on port `1025` and the
web UI on port `8025`. A digest mismatch SHALL abort before anything is installed.

#### Scenario: Mailpit captures without delivering

- **WHEN** Odoo sends mail through `127.0.0.1:1025`
- **THEN** the message appears in Mailpit's UI and API and is not delivered anywhere

### Requirement: Redirect a database's mail to the local capture

The system SHALL offer an action that, for a chosen database, points every `ir_mail_server` at
`127.0.0.1:1025` with no encryption and no credentials, and deactivates `fetchmail_server` where that table
exists. It SHALL touch only columns that exist in that database, so that it works on Odoo 12 to 19. It SHALL
require a confirmation phrase, and its prompt SHALL state that it is meant for rehearsal copies, not for a
database returning to production.

#### Scenario: A copied production database stops mailing out

- **WHEN** the redirect is applied to a database whose `ir_mail_server` points at a real SMTP host
- **THEN** that server points at `127.0.0.1:1025`, its credentials are cleared, and the next mail Odoo sends
  appears in Mailpit

#### Scenario: Refused without the phrase

- **WHEN** the operator does not type the confirmation phrase
- **THEN** the database is not modified
