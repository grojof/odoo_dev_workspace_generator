# migration-audit Specification

## Purpose
Ask one database, at any stage of a migration, for the data problems that break or distort it, read-only,
with a verdict in the exit code and the fix for each finding named, never applied.

## Requirements

### Requirement: One read-only command audits a database's coherence at any stage

The system SHALL provide `odoo-dwg migrate audit --database <db>`, accepting `--db-host`, `--db-port` and
`--db-user`. It SHALL:
- write nothing;
- prompt for nothing, the language included;
- change nothing in the database;
- exit 1 when any check found something, else 2 when any check could not be read, else 0.

It SHALL decide which checks apply from the tables and columns the database has, not from a version the
operator states. A check that does not apply SHALL be reported as not applicable, never as passed. A check
whose query fails SHALL be reported as unreadable, and the other checks SHALL still run. An invalid
database name, or a database that cannot be read at all, SHALL exit 2.

For each finding the output SHALL name what fixes it (an intake step, a decision, or a menu action), and
the command SHALL apply none of them. Examples SHALL carry ids, codes and model names, never partner names
or statement labels.

#### Scenario: A source copy before the chain

- **WHEN** the database is shaped like 12.0 and holds two journals of one company sharing a code
- **THEN** the journal check reports both, the reconciled-flag check is not applicable, and the exit code is 1

#### Scenario: A clean migrated database

- **WHEN** the database is shaped like 18.0 and no check finds anything
- **THEN** every applicable check is reported clean, the bank-line checks of sources up to 13.0 are not applicable, and the exit code is 0

#### Scenario: One table the role cannot read

- **WHEN** the query of one check fails
- **THEN** that check is reported unreadable, the others are reported with their verdicts, and the exit code is 2 unless another check found something

### Requirement: Journal codes that the unique constraint refuses are found

The audit SHALL list, per company, the journals that share a code, as a finding. Codes that differ only
by case or surrounding spaces SHALL be listed as information. It SHALL use the same grouping as the
intake's journal-code step, and name that step as the fix.

#### Scenario: Codes differing only by case

- **WHEN** one company has journals coded `CSH1` and `csh1` and no two share a code exactly
- **THEN** they are reported as information and the exit code is not raised by them

### Requirement: Bank-line problems of sources up to 13.0 are found

When the statement lines have no `move_id` column, the audit SHALL report:
- the lines imported twice, by the intake's own proof, as a finding;
- the unreconciled lines matching, by journal and amount, a posted payment line on their journal's
  default bank account that no statement line points at, as a finding. They SHALL be counted separately
  for closed and open periods, and the output SHALL say that an amount match is not proof;
- the unreconciled lines on or before the company's lock date, as information, because carrying them is
  the client's accountant's decision.

#### Scenario: A payment posted on the bank and an unreconciled line

- **WHEN** a posted payment line of 250.00 is on journal BANK1's bank account, and an unreconciled statement line of 250.00 in BANK1 is dated after the lock date
- **THEN** it is counted among the open-period lines matching a payment

### Requirement: Declared unique and check constraints missing from PostgreSQL are found

The audit SHALL list, as a finding, each `ir_model_constraint` row of type `u` of an installed module
whose table exists, when neither a constraint nor an index of that name exists. The name SHALL be
truncated to 63 bytes before comparing. Foreign-key rows SHALL not be read.

#### Scenario: A constraint OpenUpgrade could not add

- **WHEN** `ir_model_constraint` records `account_journal_code_company_uniq` for an installed module and PostgreSQL has no constraint or index of that name
- **THEN** it is reported with its model and definition

#### Scenario: A name longer than PostgreSQL keeps

- **WHEN** a recorded constraint name is 70 characters and PostgreSQL has a constraint named with its first 63
- **THEN** it is not reported

### Requirement: Required fields left empty are found

The audit SHALL count, for each stored, required, non-x2many field of a non-transient model, the records
holding no value:
- for a column that is not `NOT NULL`, a NULL value;
- for a binary field, no attachment for that record and field, and a NULL column where one exists.

Fields empty on active records, or on a table without an `active` column, SHALL be findings. Fields empty
only on archived records SHALL be information. Every identifier in the counting query SHALL be validated
and quoted.

#### Scenario: A certificate without its file

- **WHEN** a required binary field of a regular model has no attachment for one record
- **THEN** that model and field are reported with a count of 1

#### Scenario: Only archived records

- **WHEN** a required field is NULL only on records whose `active` is false
- **THEN** it is reported as information, and does not raise the exit code

### Requirement: Statement lines stored as reconciled with a suspense line are found

When the statement lines have `is_reconciled` and the journals have `suspense_account_id`, the audit SHALL
report, as a finding, the lines stored as reconciled whose entry still has an amount waiting on the
journal's suspense account, by Odoo's own rule: a line of zero amount is reconciled. It SHALL select them
with the same query the 14.0 repair uses.

#### Scenario: A line OpenUpgrade 14.0 left wrong

- **WHEN** a statement line is stored as reconciled and its entry has an amount on the suspense account
- **THEN** it is reported, with the repair named as the fix

### Requirement: Saved filters and exports naming fields the database lacks are found

When the database has saved filters and export lists, the audit SHALL report as a finding every one that
names a field or a model the database lacks. It SHALL read:
- a filter's domain leaves, the groupings and order in its context, and its sort;
- every column of an export.

It SHALL follow each path segment by segment through the fields' relations, and SHALL NOT evaluate a
domain. Examples SHALL carry the filter's or export's id, its model and the broken paths, never its name.

#### Scenario: A filter the chain moved to a rebuilt model

- **WHEN** a filter on `account.move` groups by `date_invoice:month`, which the model lacks
- **THEN** it is reported with its id, its model and that path

#### Scenario: A domain computing a date

- **WHEN** a domain compares a field with `context_today()` and every field it names exists
- **THEN** it is not reported

#### Scenario: An export on a model that is gone

- **WHEN** an export's model no longer exists
- **THEN** it is reported as naming a model that is gone
