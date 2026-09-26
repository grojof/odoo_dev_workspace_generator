# Spec Delta

## ADDED Requirements

### Requirement: The taxes OpenUpgrade 13.0 adds to a reused journal item are taken back after the 13.0 step

For a chain whose source is 12.0 or older, the driver SHALL keep the source's journal-item taxes. It SHALL do
this right after restoring the source dump into the working database, and before the source checkpoint:
- every row of `account_move_line_account_tax_rel` goes into a table of its own;
- that table holds the highest journal-item id of the source too.

After the 13.0 step, after its post hook and before neutralising and checkpointing, the driver SHALL take
back from each reused journal item every tax that it did not bear in the source and that its invoice line
bore. A reused journal item is one that existed in the source and that OpenUpgrade 13.0 linked to an invoice
line. No other tax of any journal item SHALL be changed.

The repair SHALL:
- run in one transaction;
- write each tax it took back to a file in the environment's logs (journal item, move, tax, amount);
- print how many taxes it took back and from how many items;
- record the repair in the step record;
- drop its tables.

When the kept taxes are absent (a source checkpoint taken without them), it SHALL change nothing and say
that only a run from the source dump can repair it.

#### Scenario: A 12.0 → 18.0 chain

- **WHEN** the driver of a 12.0 → 18.0 chain is generated
- **THEN** its source restore keeps the journal items' taxes before the source checkpoint, and its 13.0
  block takes back the added taxes after the post hook and before the checkpoint

#### Scenario: A 13.0 source

- **WHEN** the driver of a 13.0 → 18.0 chain is generated
- **THEN** it keeps no taxes and no step takes any back

#### Scenario: An item grouped in the source

- **WHEN** a source journal item bore taxes A and B, and OpenUpgrade 13.0 linked it to an invoice line
  bearing A and C, and gave it A, B and C
- **THEN** after the 13.0 step it bears A and B again, and C is listed as taken back

#### Scenario: A tax changed for another reason

- **WHEN** an item bears a tax it did not bear in the source, and its invoice line did not bear that tax
  either
- **THEN** that tax stays

#### Scenario: A checkpoint without the kept taxes

- **WHEN** the run resumes from a source checkpoint taken before the driver kept the taxes
- **THEN** the 13.0 step changes no tax, and says that only a run from the source dump repairs them
