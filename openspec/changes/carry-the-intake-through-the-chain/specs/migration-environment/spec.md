# Spec Delta

## ADDED Requirements

### Requirement: A chain generated after an intake carries it through every step

After a client intake, generation SHALL propose the OCA repositories to clone. It SHALL propose:
- every repository the intake's availability check found an installed module in, at any step of the
  chain;
- the repositories already linked.

The operator MAY edit the list. A core module found in an OCA repository at a later step SHALL count as
moved, because the client never used that repository and the chain has to clone it.

Every step's configuration SHALL name the environment's `data_dir`, the one the source and
`open_for_testing.sh` use. After every restore of the working database, whether of the source dump or of
a checkpoint, the driver SHALL give that database a filestore of hard links to the reference's, unless it
already has one. Without an intake, neither changes.

#### Scenario: A core module that moves to OCA

- **WHEN** the availability table finds a core module in `bank-statement-import` from 14.0
- **THEN** generation proposes `bank-statement-import`, and the module counts as moved

#### Scenario: The migrated database opens with its attachments

- **WHEN** the driver restores the source dump into its working database
- **THEN** that database has the reference's files as hard links in the environment's `data_dir`, and
  every step's configuration names that `data_dir`
