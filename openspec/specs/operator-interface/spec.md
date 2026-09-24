# operator-interface Specification

## Purpose

The terminal surface: how the tool is started, what language it speaks, how a menu behaves, what happens when something goes wrong, and what colour is allowed to mean. Generated artifacts are outside it — they are English whatever the operator's UI is.

## Requirements

### Requirement: One tool, three sections, two ways in

The tool SHALL be runnable as `python -m odoo_dwg`, as the `odoo-dwg` console script and as the repository
script, all reaching the same entry point. With no subcommand it SHALL open the interactive menu; with one
(`workspace`, `provision`, `migrate`) it SHALL open that section directly. `--version` SHALL print the
version and exit.

#### Scenario: A section is reached without the menu

- **WHEN** the tool is started with `migrate`
- **THEN** the migration section opens directly, and leaving it ends the run

### Requirement: English is the source language; Spanish is an optional UI

Every operator-facing string SHALL be an English literal in the code, translated at display time through a
catalog keyed by that literal, so a string missing from the catalog degrades to English rather than failing.
The catalog SHALL be authored in the direction it is read (English → Spanish); an inverted one would merge
two English strings whose Spanish happened to match. Technical terms a Spanish-speaking Odoo developer says
in English SHALL be left in English, and the sentence around them translated.

The UI language SHALL be taken from `--lang`, else `ODWG_LANG`, else a prompt at startup, and SHALL be
settled before the help text is built, so `--help` is shown in the chosen language too.

A read-only command SHALL NOT prompt for the language, and neither SHALL anything run without a terminal
on stdin: with no `--lang` and no `ODWG_LANG`, both SHALL use English.

**Generated artifacts SHALL NOT be translated.** Every file the tool writes — configs, scripts, editor
files, READMEs, the migration driver, staging reports and scaffolds — SHALL be English whatever the UI
language is: they are technical, they are read by other tools, and they outlive the session that wrote them.

**The one exception is a report written for a client.** It SHALL be rendered in a language chosen for that
report, English or Spanish, whatever the UI language is. Its labels SHALL come from the same catalog.
Choosing the language per report, rather than taking the session's, keeps the report independent of who
rendered it: an English session can hand a Spanish-speaking client a Spanish report, and the reverse.

#### Scenario: An untranslated string still reads

- **WHEN** the UI language is Spanish and a string is absent from the catalog
- **THEN** the English text is shown, and nothing fails

#### Scenario: A Spanish session writes English files

- **WHEN** a workspace or a migration environment is generated with the UI in Spanish
- **THEN** every generated file is byte-for-byte what an English session would have written

#### Scenario: A client report in the client's language

- **WHEN** a client report is rendered in Spanish from a session whose UI is English
- **THEN** the report's labels are Spanish, and rendering it from a Spanish session yields the same bytes

### Requirement: Menus and prompts behave the same everywhere

Every menu SHALL be a numbered list with `0` as the leave-without-acting entry. Options SHALL be shown
translated while the flow compares the English original, so a translation can never change what a choice
does. The same sentinel SHALL be returned for `0`, for an empty answer with no default, and for an
out-of-range one, so no caller can mistake a cancellation for a choice.

A yes/no prompt SHALL state its default and SHALL accept both languages' words. A prompt that asks for an
existing file SHALL offer a browser over the filesystem, SHALL warn — without refusing — when the chosen
path does not carry the expected extension, and SHALL start where the operator last chose. A directory it
cannot read SHALL be reported and stepped out of, not raised.

#### Scenario: Cancelling a menu changes nothing

- **WHEN** the operator answers `0` at any menu
- **THEN** the flow returns without planning or running anything

#### Scenario: A translated option still selects the same thing

- **WHEN** the operator picks an option from the Spanish menu
- **THEN** the flow receives the English original, and behaves as it would in English

### Requirement: A failure returns the operator to the menu

An error a flow cannot use — a malformed profile, an unreadable file, a plan whose step failed — SHALL be
reported on one line and SHALL return to the menu, never as a traceback. An interrupt SHALL abandon the
action in progress and return to the menu; input closing SHALL exit cleanly. A run started at a section
rather than the menu SHALL exit non-zero on such an error, so it can be used from a script.

#### Scenario: A failed plan does not end the session

- **WHEN** a step of an applied plan fails
- **THEN** the failure is reported and the menu is shown again

#### Scenario: A section run reports failure to its caller

- **WHEN** the tool is started with `provision` and the flow fails
- **THEN** it exits non-zero

### Requirement: Colour is a courtesy, never the message

Output SHALL be coloured only when it goes to a terminal that supports it, SHALL be plain when `NO_COLOR` is
set whatever the terminal is, and SHALL be coloured when `FORCE_COLOR` is set and `NO_COLOR` is not. No
state SHALL be conveyed by colour alone: every level carries its own word.

Text the tool did not write — a value read from a database, a file or another tool's output — SHALL NOT be
able to drive the terminal: what is printed inside a table SHALL carry colour and nothing else.

#### Scenario: A pipe gets plain text

- **WHEN** output is redirected to a file
- **THEN** it contains no escape sequences, and every state is still named in words

#### Scenario: A module name cannot repaint the screen

- **WHEN** a module name read from the database under migration contains a terminal control sequence
- **THEN** the table prints the name without it, and the table's own columns still line up

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
