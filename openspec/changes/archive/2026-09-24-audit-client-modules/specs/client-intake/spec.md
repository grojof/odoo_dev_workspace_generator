# Spec Delta

## ADDED Requirements

### Requirement: The client's own modules are audited from their data

The system SHALL offer an intake step that audits every installed module the intake classified as the
client's own, reading the reference only. The operator MAY name other modules. For each module it SHALL
record:
- the installed modules that depend on it;
- each model it created, with its rows and the rows written since a date the operator gives. For a
  transient model, instead, the times it was opened, read from its id sequence;
- each stored field it created, with the rows holding a value and the rows written since the date with a
  value, and the last such write. `false` and the empty string SHALL NOT count as values. A related field
  SHALL be marked recomputed;
- each many2many table it created, with its rows;
- each document (report action) it declares, with:
  - its model;
  - whether it is in the Print menu;
  - whether it is registered under another module's namespace;
  - the attachments named as it names its PDF, in total and since the date;
- whether OCA publishes a module of the same name, from the cached OCA trees.

A module SHALL be labelled from that evidence:
- *no data* when nothing it created holds a value or a row, and no wizard of it was ever opened;
- *not used since <date>* when it holds data but none was written since the date and no print of its
  documents was counted since it;
- otherwise *in use*.

The label is evidence for the operator's decision, not the decision.

Given a migrated database, the step SHALL also record, for every field and table, whether it exists there
and holds the same number of values.

Given a web access log (Odoo's own or a proxy's), the step SHALL count, per document, the requests to
`/report/<pdf|html>/<document>/` since the date. A print is not recorded anywhere else: Odoo stores no row
for it, and a production log at `log_level = warn` sets `werkzeug:WARNING` and records no request.

The step SHALL record the table and one finding. If it cannot read the reference, it SHALL say it could
not tell, and record nothing.

#### Scenario: A field used last in 2022

- **WHEN** a module's only field holds a value on one row, last written in 2022, and the date is 2025-01-01
- **THEN** the module is labelled not used since 2025-01-01

#### Scenario: A document printed through the proxy

- **WHEN** the access log holds three `GET /report/pdf/acme_reports.invoice/42` requests since the date
- **THEN** that document's prints are three, and its module is in use

#### Scenario: A document under another module's namespace

- **WHEN** a client module declares its report action as `account.report_acme_invoice`
- **THEN** the audit flags it, because updating `account` in the chain can remove or overwrite it
