# Spec Delta

## ADDED Requirements

### Requirement: Grouped invoice items become the invoice lines they stand for, after the target step

For a chain whose source is 12.0 or older and whose target is 16.0 or later, the driver SHALL repair the
invoices whose journal items were grouped at the source. It SHALL run right after the target step and its
post hook, and before neutralising and checkpointing.

A grouped item is a journal item of an invoice or credit note that:
- OpenUpgrade 13.0 excluded from the invoice tab;
- is typed as a product line;
- has no invoice line of its own.

The repair SHALL work on each group of one move, one account and one set of taxes. A group is repaired when:
- its grouped items and its zero-amount invoice lines add up to the same amount, in the document's
  direction;
- the move is in its company's currency;
- no grouped item of the group is reconciled, partly or fully;
- nothing points at a grouped item that the repair does not know how to move.

A zero-amount invoice line SHALL be keyed on its own source invoice line's taxes when these are known, and
SHALL take them. When the move has a single grouped account and its lines add up to it, the lines SHALL
take that account.

In a repaired group:
- each invoice line SHALL take its own amount, in the document's direction, with the grouped item's
  partner;
- the cents of rounding SHALL go to the group's largest line;
- on a reconcilable account, each line SHALL stay open for its amount, as the grouped item was;
- a many-to-many link to a grouped item SHALL be copied to every line of the group;
- a known single reference SHALL move to the group's largest line: an analytic line, and an EC sales list
  record or refund detail;
- the grouped items SHALL then be deleted.

Other groups SHALL be left as they are, with the reason for each.

The repair SHALL run in one transaction and commit only if all of these hold:
- every changed move is balanced;
- per move, the balance of each account, of each account and partner, and of the lines bearing each tax is
  unchanged, and so is the amount still open per account and partner;
- the invoices' stored amounts are unchanged;
- no link to a deleted item is lost, and no reference to one either: each analytic line and detail is
  still there.

Otherwise it SHALL keep nothing and stop the run, naming the check that failed. It SHALL print the groups
it repaired and left, record the repair in the step record, and write the groups it left, with the reason,
to a file in the environment's logs. It SHALL do nothing when the database has no grouped items or lacks
the columns it reads.

#### Scenario: A 12.0 → 18.0 chain

- **WHEN** the driver of a 12.0 → 18.0 chain is generated
- **THEN** its 18.0 block repairs the grouped invoice items after the post hook and before the checkpoint,
  and no other step does

#### Scenario: A chain that does not need it

- **WHEN** the driver of a 13.0 → 18.0 or of a 12.0 → 15.0 chain is generated
- **THEN** no step repairs grouped invoice items

#### Scenario: An invoice with two products grouped into one item

- **WHEN** a posted invoice has two invoice lines at zero amount and one grouped item on their account and
  taxes that carries their sum
- **THEN** each invoice line carries its own amount, the grouped item is gone, and the move, its accounts,
  its partners and its taxes add up as before

#### Scenario: Lines that cancel out

- **WHEN** an invoice has a line and its opposite on one account, under different taxes, grouped into one
  item per tax
- **THEN** each line takes its own signed amount from the item with its taxes, and each tax's base is
  unchanged

#### Scenario: A group that does not add up

- **WHEN** a grouped item's amount differs from the sum of the invoice lines on its account and taxes
- **THEN** that group is left grouped, is named with its reason, and the other groups of the move are
  still repaired

#### Scenario: A check that fails

- **WHEN** any of the checks does not hold after the repair
- **THEN** the database is left as the target step left it and the run stops naming the check

#### Scenario: A resumed run

- **WHEN** a run resumes after the target checkpoint
- **THEN** the repair does not run again, since the checkpoint already holds its result
