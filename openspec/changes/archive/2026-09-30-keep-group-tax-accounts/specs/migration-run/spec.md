## ADDED Requirements

### Requirement: Former group taxes get their children's accounts after the 13.0 step

For a chain whose source is 12.0 or older, right after the 13.0 step and the taxes taken back, and before
neutralising and checkpointing, the driver SHALL give each tax repartition line that has no account, of a
tax that has children, the account of its child's repartition line for the same document (invoice or
refund), repartition type and sign. OpenUpgrade 13.0 creates those lines for a localisation's group taxes
and takes their account from the group, which holds none.

It SHALL NOT write a line that has an account, nor a base line, nor set an account from a child's line that
has none. It SHALL list every line written, with its tax, document, factor and account, in
`logs/13.0-group-tax-accounts.tsv`, and record the repair in the step record. A chain whose source is 13.0
or later SHALL NOT run it.

#### Scenario: A reverse charge tax that was a group

- **WHEN** a 12.0 group tax has a child at +21 % on account 472 and a child at -21 % on account 477, and
  OpenUpgrade 13.0 left the group's tax repartition lines without account
- **THEN** its +100 % lines take 472 and its -100 % lines take 477, for invoices and for refunds, and each
  is listed

#### Scenario: A company's own account

- **WHEN** the child tax posts to an account of the company's own
- **THEN** the group's line takes that account, not a standard one

#### Scenario: OpenUpgrade already set the accounts

- **WHEN** the group's tax repartition lines already have their accounts
- **THEN** nothing is written and the list is empty
