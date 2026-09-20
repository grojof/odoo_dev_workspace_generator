# operator-interface Specification Delta

## ADDED Requirements

### Requirement: The read-only answers are available without the menu

Every answer the tool can give that changes nothing SHALL be obtainable from a non-interactive command, so
that it can be had from a script, from a pipe, or from a second terminal while a migration runs.

Such a command SHALL write nothing, SHALL require no terminal, and SHALL NOT prompt. It SHALL exit zero
when it found nothing to report and non-zero when it did, so that its verdict is usable by a script and not
only by a reader.

Anything that changes the host SHALL remain behind the interactive flow and its confirmation phrase. A
read-only command that finds something to act on SHALL name the menu action to use, and SHALL NOT perform
it.

#### Scenario: A check in a script

- **WHEN** `odoo-dwg mail check --database acme_copy` is run on a database that can still mail out
- **THEN** it prints the verdict and exits non-zero, having issued no statement that writes

#### Scenario: Nothing to report

- **WHEN** the same command is run on a captured database
- **THEN** it says so and exits zero

#### Scenario: A finding names the action, not performs it

- **WHEN** a read-only check finds a database that should be captured
- **THEN** it names the menu action that captures it, and captures nothing
