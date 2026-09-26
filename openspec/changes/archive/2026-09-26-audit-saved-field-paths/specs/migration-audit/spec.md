# Spec Delta

## ADDED Requirements

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
