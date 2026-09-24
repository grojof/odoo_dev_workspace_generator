# Spec Delta

## ADDED Requirements

### Requirement: Unreconciled bank lines of closed periods can be left behind, on the accountant's decision

The bank statement step SHALL also list, for a source up to 13.0, the unreconciled lines dated on or
before the later of their company's fiscal-year and period lock dates, other than the certain duplicates.
A line whose exact amount matches an open receivable or payable item of the same partner SHALL be kept
and listed apart. The others SHALL be listed with journal, date, amount, label, reference, partner, note and
statement, as the file to deliver.

The step SHALL write a separate SQL file that deletes a listed line only while no journal item points at
it and its date is still on or before its company's lock date. It SHALL change nothing itself, and its
finding SHALL say that applying the file is the client's accountant's decision.

#### Scenario: A closed-period line with no match is listed to leave behind

- **WHEN** the lock date is 31 July and an unreconciled line of 3 March matches no open item
- **THEN** it is in the table and in the SQL

#### Scenario: A closed-period line matching an open invoice is kept

- **WHEN** an unreconciled line of 3 March has the exact amount of an open invoice of the same partner
- **THEN** it is listed as kept and is not in the SQL

#### Scenario: A line after the lock date is ongoing work

- **WHEN** an unreconciled line is dated after the lock date
- **THEN** it is in neither the table nor the SQL
