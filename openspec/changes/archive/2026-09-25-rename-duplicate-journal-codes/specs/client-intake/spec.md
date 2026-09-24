# Spec Delta

## ADDED Requirements

### Requirement: Journal codes the target refuses are found and renamed before the chain

The system SHALL offer an intake step that reads the reference only and finds, per company, the journals
that share a code, and those whose codes differ only by case or surrounding spaces. In each group the
journal with most entries SHALL keep its code, the lowest id on a tie. Every other journal SHALL get a
proposed code of 1 to 5 letters or digits, unique in its company.

The step SHALL write a table the operator may edit. On a later run it SHALL keep the codes the operator
wrote there, and refuse, naming them, codes that are not 1 to 5 letters or digits or not unique in the
company. It SHALL write a SQL file that changes a journal's code only while the journal still has its old
code and no journal of its company has the new one, and one finding. It SHALL change nothing itself.

#### Scenario: Two journals share a code

- **WHEN** journals 101 (900 entries) and 102 (40 entries) of one company both have code `BANK1`
- **THEN** 101 keeps `BANK1`, 102 gets a proposed code unused in the company, and the SQL renames 102 only

#### Scenario: Codes that differ only by a space

- **WHEN** one journal has `CASH` and another `CASH `
- **THEN** they are one confusable group, and the one with fewer entries gets a proposal

#### Scenario: The operator's code is kept, a bad one refused

- **WHEN** the operator writes `ACME1` for journal 102 in the table and re-runs the step
- **THEN** the SQL uses `ACME1`, and a code such as `AC ME` or one already used in the company stops the step with its name

#### Scenario: The constraint is added after the SQL

- **WHEN** the SQL has run on a copy
- **THEN** `unique (company_id, code)` can be added to `account_journal`, and running the SQL again changes nothing
