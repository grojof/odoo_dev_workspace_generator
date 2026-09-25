# Spec Delta

## ADDED Requirements

### Requirement: The operator may give any journal a readable code

The journal codes step SHALL accept, in the table it writes and reads back, a code for any journal of the
company: journals outside every group, and the journal that keeps a group's code, included. A journal
outside every group that the operator renames SHALL appear in the plan as renamed by the operator. A code
equal to the journal's current code SHALL rename nothing. A new code that is another journal's current
code SHALL be refused, naming both journals. Codes SHALL still be 1 to 5 letters or digits and unique in
the company once every rename applies. The SQL SHALL be guarded as for the other renames.

#### Scenario: A journal with a unique but unclear code

- **WHEN** the operator writes `BAN01` for a journal whose code `BNK1` no other journal shares
- **THEN** the plan renames it as the operator's, and the SQL renames it while it still has `BNK1` and `BAN01` is free

#### Scenario: The journal that keeps a group's code gets a readable one

- **WHEN** the operator writes `ESB01` for the journal that would keep the shared `BANK1`
- **THEN** it is renamed to `ESB01`, and the others of the group get their own codes

#### Scenario: A chained rename is refused

- **WHEN** the operator gives journal A the current code of journal B
- **THEN** the step stops and names both journals
