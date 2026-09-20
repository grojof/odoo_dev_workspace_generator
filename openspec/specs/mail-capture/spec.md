# mail-capture Specification

## Purpose

Lets Odoo's mail be read without being delivered. A loopback-only Mailpit receives what the generated `odoo.conf` sends. For a database whose own mail servers would bypass `odoo.conf`, actions capture its mail, give the configuration back, and say whether mail can leave — the capture moving no value the client configured, so the database it is applied to can still go into production.

## Requirements

### Requirement: Optional Mailpit installation

`provision apply` SHALL offer, as an opt-in step, to install Mailpit from a pinned upstream release verified
by its SHA-256 digest. It SHALL run as a system service bound to `127.0.0.1`, with SMTP on port `1025` and the
web UI on port `8025`. A digest mismatch SHALL abort before anything is installed.

#### Scenario: Mailpit captures without delivering

- **WHEN** Odoo sends mail through `127.0.0.1:1025`
- **THEN** the message appears in Mailpit's UI and API and is not delivered anywhere

### Requirement: Mail is captured without losing the way back

The system SHALL offer an action that stops a database's mail leaving the host **without altering any
existing mail configuration**. It SHALL deactivate the active `ir_mail_server` rows, deactivate
`fetchmail_server` rows where that table exists, and add one mail server of its own pointing at the local
capture with a sequence that makes Odoo prefer it.

The added server SHALL be derived from an existing row of that database's own `ir_mail_server`, overriding
only the fields the capture defines, so that it satisfies whatever columns that version of Odoo requires.
Where the table has no rows to derive from, the action SHALL add none and SHALL say that Odoo will fall
back to the configuration file.

The action SHALL record, inside the same database, which rows it deactivated and which it added, so the
record survives the dump and restore of every migration step.

Applying it twice SHALL leave the capture in effect: the second application SHALL NOT deactivate the server
the first one added.

A database named by the operator MUST be a valid PostgreSQL database name before any command is built with
it; otherwise the action SHALL stop naming the value.

#### Scenario: A copied production database stops mailing out

- **WHEN** capture is applied to a database whose `ir_mail_server` points at a real SMTP host
- **THEN** that server is deactivated with its host, user and password unchanged, a server pointing at the
  capture is added and preferred, and the next mail Odoo sends appears in Mailpit

#### Scenario: Capturing twice still captures

- **WHEN** capture is applied to a database it has already captured
- **THEN** the server it added before is still the active one

#### Scenario: An invalid database name is refused

- **WHEN** the operator names `db"; DROP DATABASE x --` as the database to capture
- **THEN** the action stops naming the value, and no command is planned

### Requirement: The captured configuration can be given back

The system SHALL offer an action that returns a captured database to the mail configuration it had. It
SHALL remove the server capture added, reactivate exactly the rows capture deactivated, and remove its
record from the database.

It SHALL reactivate no row it did not deactivate: a mail server the client had switched off SHALL stay off.

Where no capture is recorded, the action SHALL say so and change nothing, rather than reporting success.

Rows that capture deactivated and that no longer exist SHALL be reported rather than passed over, because a
mail server a migration removed is a difference between the database that was captured and the one being
handed back.

#### Scenario: Production mail works on the day it goes live

- **WHEN** restore is run on the database a migration chain produced
- **THEN** the client's own mail server is active again with the host, user and password it had before the
  capture, fetchmail is running again, and the capture's server and record are gone

#### Scenario: A server the client had disabled stays disabled

- **WHEN** restore is run on a database that had an inactive mail server before capture
- **THEN** that server is still inactive

#### Scenario: Nothing to restore

- **WHEN** restore is run on a database that was never captured
- **THEN** it reports that no capture is recorded and changes nothing

### Requirement: Whether mail can leave is answerable without changing anything

The system SHALL offer a read-only action that reports, for a chosen database, whether mail can leave the
host: every active mail server with the host and port it points at, whether any fetchmail server is
active, and whether a capture is in effect.

It SHALL state the verdict, not only the rows: a database with an active mail server pointing anywhere but
the capture SHALL be reported as able to mail out. A database with no active mail server SHALL be reported
as falling back to the configuration file, which the action SHALL NOT assume points at the capture.

The action SHALL NOT require a confirmation phrase and SHALL issue no statement that writes.

#### Scenario: A database that can still mail out

- **WHEN** the check is run on a database with an active server pointing at a real SMTP host
- **THEN** it names that server and reports that mail can leave

#### Scenario: A captured database

- **WHEN** the check is run on a captured database
- **THEN** it reports the capture in effect and that the client's servers are deactivated, not lost
