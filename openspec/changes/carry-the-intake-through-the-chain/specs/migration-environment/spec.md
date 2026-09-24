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

Each step's venv SHALL get the Python libraries the installed modules declare at that step, read from that
step's manifests under the name the step knows each module by. They SHALL be held to what the venv already
holds, so a library that needs another version of something Odoo pinned fails by name instead of upgrading
it. Before each step, the driver SHALL check those libraries with the step's own interpreter, as Odoo does:
the distribution and its version, then the import name. It SHALL stop before the step and name each module
and library that is missing or at the wrong version.

#### Scenario: A library only the source's venv had

- **WHEN** a module at 13.0 declares `unidecode` and the 13.0 venv lacks it
- **THEN** the driver stops before the step and names the module and the library, and regenerating the
  environment offers to install it in that venv

#### Scenario: A core module that moves to OCA

- **WHEN** the availability table finds a core module in `bank-statement-import` from 14.0
- **THEN** generation proposes `bank-statement-import`, and the module counts as moved

#### Scenario: The migrated database opens with its attachments

- **WHEN** the driver restores the source dump into its working database
- **THEN** that database has the reference's files as hard links in the environment's `data_dir`, and
  every step's configuration names that `data_dir`
