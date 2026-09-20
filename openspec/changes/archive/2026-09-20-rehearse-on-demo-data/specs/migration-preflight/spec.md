# migration-preflight Specification Delta

## ADDED Requirements

### Requirement: What the chain does to a module is answerable before running it

For each module named, the system SHALL report what the chain declares will happen to it and at which
step: **renamed** to another name, **merged** into another module — absorbed, its records folded into the
successor — or **nothing declared**, which means the module is expected to carry on under its own name.

Renamed and merged SHALL be distinguished. They differ in what becomes of the module's own records, and a
reader told only "the successor is X" cannot tell which happened.

Each answer SHALL name the step whose `apriori.py` declared it. Where a step's `apriori.py` cannot be read,
the system SHALL say so for that step rather than report the module as unchanged, because an unread source
is not a source that declared nothing.

A chain SHALL be able to suggest a set of modules that exercises the different fates, drawn from what is
actually present under the source version's OCA directory: a module absent at the source version cannot be
installed there, and suggesting it would produce a rehearsal that fails for the wrong reason.

#### Scenario: A module absorbed into another

- **WHEN** the operator asks about a module that `apriori.py` merges into `website_sale` at 14.0
- **THEN** it is reported as merged into `website_sale` at 14.0, distinctly from a rename

#### Scenario: A module nothing declares

- **WHEN** no step of the chain declares a fate for the module
- **THEN** it is reported as expected to carry on under its own name

#### Scenario: A step whose sources cannot be read

- **WHEN** a step's `apriori.py` is missing from the clone
- **THEN** that step is reported as unread, and no module is reported unchanged on the strength of it
