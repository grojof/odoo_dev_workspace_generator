# Spec Delta

## MODIFIED Requirements

### Requirement: English is the source language; Spanish is an optional UI

Every operator-facing string SHALL be an English literal in the code, translated at display time through a
catalog keyed by that literal, so a string missing from the catalog degrades to English rather than failing.
The catalog SHALL be authored in the direction it is read (English → Spanish); an inverted one would merge
two English strings whose Spanish happened to match. Technical terms a Spanish-speaking Odoo developer says
in English SHALL be left in English, and the sentence around them translated.

The UI language SHALL be taken from `--lang`, else `ODWG_LANG`, else a prompt at startup, and SHALL be
settled before the help text is built, so `--help` is shown in the chosen language too.

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
