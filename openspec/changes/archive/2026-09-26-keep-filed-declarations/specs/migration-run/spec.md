# Spec Delta

## ADDED Requirements

### Requirement: Filed declarations keep their boxes through the chain

The driver SHALL copy the source's filed declarations into tables of its own, right after restoring the
source dump and before the source checkpoint:
- every stored box;
- the box's links to journal items;
- the map lines and maps the boxes point at.

At the target, after the post hook and before the grouped-items repair, it SHALL put back every map, map
line, box and link the chain deleted, with the source's ids, casting each column the target still has to the
target's type. It SHALL:
- put back no link to a journal item the chain no longer has, and count such links;
- check that every box the source held exists with its declaration, number and filed amount, and otherwise
  keep nothing and stop the run;
- list each box it put back in a file in the environment's logs, record the repair in the step record, and
  drop its tables.

When the copies are absent (a source checkpoint taken without them), it SHALL change nothing, record the
repair as skipped, and say that only a run from the source dump checks them.

#### Scenario: A map a later module version no longer ships

- **WHEN** a module update in the chain deletes an older map's lines, and with them a filed return's boxes
  and links
- **THEN** at the target the boxes are back with their ids and amounts, their map line and map are back,
  and their links are back to every journal item that still exists

#### Scenario: A box that no longer holds its filed amount

- **WHEN** a box the source held exists at the target with another amount
- **THEN** nothing is put back and the run stops naming the check

#### Scenario: A checkpoint without the copies

- **WHEN** the run resumes from a source checkpoint taken before the driver kept the declarations
- **THEN** nothing is put back, and the step record and output say the check was skipped
