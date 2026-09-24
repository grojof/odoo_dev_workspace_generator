# Spec Delta

## MODIFIED Requirements

### Requirement: A finding carries its evidence and how to re-derive it

Every finding SHALL have:

- **an id:** lower-case kebab-case, unique in the ledger, and not the id of a withdrawn finding;
- **the date it was found;**
- **the phase it was found in;**
- **a severity:** one of `critical`, `high`, `medium`, `low`, `info`;
- **a category;**
- **an audience:** `client` or `internal`;
- **the subject it is about;**
- **a technical summary;**
- **evidence:** the structured facts it rests on;
- **the query or command that re-derives it;**
- **the proposed action;**
- **a decision.**

A finding without evidence, or without a re-deriving query, SHALL be refused. A number shown to anyone is
only as good as the query that produced it, and a count quoted from memory is how the first client intake
reported a figure that a query then corrected.

A finding MAY carry client-facing text, per language:
- a title;
- a plain explanation;
- the question the client has to answer, if any;
- optionally, a level that overrides where the client report places it.

A finding MAY attach tables from `findings/data/`, each marked for the client or internal.

A finding SHALL hold no key besides these, `history` and `client`. A key the ledger does not know SHALL be a
validation problem that names it: the ledger is rewritten by the tool, and a key it validated but does not
model would be dropped on the next write.

#### Scenario: A finding without a query

- **WHEN** a finding is added with evidence but no re-deriving query
- **THEN** it is refused, the refusal names the missing field, and the ledger is unchanged

#### Scenario: A duplicate id

- **WHEN** a finding is added whose id is already in the ledger, or belongs to a withdrawn finding
- **THEN** it is refused, and the ledger is unchanged

#### Scenario: A key the ledger does not know

- **WHEN** a finding carries a key outside its declared fields
- **THEN** validation names the finding and the key, and the ledger is not accepted
