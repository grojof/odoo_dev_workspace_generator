# Spec Delta

## ADDED Requirements

### Requirement: Bank statement lines imported twice are found from the bank's own balances

For a source up to 13.0, the system SHALL offer an intake step that reads the reference only and finds
the bank statement lines imported more than once. It SHALL treat as proven only:
- statements whose opening balance plus their lines equals their closing balance;
- a day that two or more such statements of the same journal hold with identical content (journal, date,
  amount, label, reference, note and partner name of every line) and the same end-of-day balance.

Within such a day, each movement SHALL be its line content plus its occurrence index, so two identical
movements inside one day are two movements. Of each movement's copies, one SHALL be kept: a reconciled one
if any, else the lowest id.

The step SHALL record:
- each other unreconciled copy, as a duplicate with the line it duplicates;
- each other reconciled copy, as a movement reconciled more than once;
- how many statements match their file;
- how many unreconciled lines remain, and how many fall after the company's lock date.

It SHALL write the table, a SQL file that deletes a listed line only while it has no journal item and its
kept twin still exists with the same content, and one finding. It SHALL delete nothing itself. A source
from 14.0, or a reference it cannot read, SHALL be refused with the reason, and nothing recorded.

#### Scenario: A bank day imported twice

- **WHEN** two statements of one journal that match their files both hold 3 March with the same lines and the same end-of-day balance, and one copy's lines are reconciled
- **THEN** the other copy's unreconciled lines are listed as duplicates of the reconciled ones

#### Scenario: Two equal fees on one day are not a duplicate

- **WHEN** one statement holds two identical 1.50 fee lines on the same day and no other statement holds that day
- **THEN** neither line is listed

#### Scenario: A movement reconciled in both copies

- **WHEN** a day imported twice has the same movement reconciled in both statements
- **THEN** it is recorded as reconciled more than once, and not in the SQL file

#### Scenario: A statement that does not match its file proves nothing

- **WHEN** a statement's lines do not add up to its closing balance
- **THEN** none of its days is used as proof
