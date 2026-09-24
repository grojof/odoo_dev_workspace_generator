# migration-findings Specification

## Purpose
Record what a migration finds, with the evidence behind each finding and the client's decision on it, in
one ledger per migration environment, and render the client and extended reports from that ledger alone.

## Requirements

### Requirement: One ledger per migration environment

Each migration environment SHALL keep its findings in one ledger, `findings/findings.json` under the
environment's root. Tables that findings cite SHALL live beside it in `findings/data/`, as tab-separated
files whose first row is the header.

The ledger SHALL carry:

- **a schema version;**
- **the client's name and the database;**
- **the source and target versions;**
- **the reference database:** the restored copy that is never modified;
- **a context block:**
  - what was received, with dates;
  - the versions involved, each with a reference link;
  - where the code comes from, each source with its link, or marked private;
- **the phases of the migration,** each with a state of `pending`, `in-progress` or `done`;
- **the findings;**
- **a corrections log.**

The system SHALL refuse a ledger whose schema version it does not know, rather than read it as a
different one.

#### Scenario: A new environment has no ledger yet

- **WHEN** an environment has no `findings/findings.json`
- **THEN** listing its findings says there is no ledger yet and names the menu action that starts one,
  and nothing fails

#### Scenario: A ledger from a later version of the tool

- **WHEN** the ledger declares a schema version this tool does not know
- **THEN** the system refuses to read it, names the version it found and the versions it knows, and
  writes nothing

### Requirement: A finding carries its evidence and how to re-derive it

Every finding SHALL have:

- **an id:** lower-case kebab-case, unique in the ledger, and not the id of a withdrawn finding;
- **the date it was found;**
- **the phase it was found in;**
- **a severity:** one of `critical`, `high`, `medium`, `low`, `info`;
- **a category;**
- **an audience:** `client` or `internal`;
- **the subject it is about;**
- **a technical summary;**
- **evidence:** the structured facts it rests on;
- **the query or command that re-derives it;**
- **the proposed action;**
- **a decision.**

A finding without evidence, or without a re-deriving query, SHALL be refused. A number shown to anyone is
only as good as the query that produced it, and a count quoted from memory is how the first client intake
reported a figure that a query then corrected.

A finding MAY carry client-facing text, per language:
- a title;
- a plain explanation;
- the question the client has to answer, if any;
- optionally, a level that overrides where the client report places it.

A finding MAY attach tables from `findings/data/`, each marked for the client or internal.

A finding SHALL hold no key besides these, `history` and `client`. A key the ledger does not know SHALL be a
validation problem that names it: the ledger is rewritten by the tool, and a key it validated but does not
model would be dropped on the next write.

#### Scenario: A finding without a query

- **WHEN** a finding is added with evidence but no re-deriving query
- **THEN** it is refused, the refusal names the missing field, and the ledger is unchanged

#### Scenario: A duplicate id

- **WHEN** a finding is added whose id is already in the ledger, or belongs to a withdrawn finding
- **THEN** it is refused, and the ledger is unchanged

#### Scenario: A key the ledger does not know

- **WHEN** a finding carries a key outside its declared fields
- **THEN** validation names the finding and the key, and the ledger is not accepted

### Requirement: Decisions are recorded, and earlier ones are kept

A finding's decision SHALL be one of:

| Decision | Meaning |
|---|---|
| `pending` | not yet decided |
| `accepted` | acknowledged, nothing to do |
| `act` | the proposed action is approved |
| `declined` | the action is refused |

Recording a decision SHALL keep:
- the decision;
- the date;
- a note (who decided and why, in the operator's words).

The decisions a finding had before SHALL be kept in its history, not overwritten, so the extended report
can show when a client changed their mind.

#### Scenario: The client changes their mind

- **WHEN** a finding decided `act` is later decided `declined`
- **THEN** the finding's decision is `declined`, and its history still shows the earlier `act` with its
  date and note

### Requirement: A withdrawn finding is corrected, not deleted

Withdrawing a finding SHALL move it from the findings to the corrections log, with the date and the reason
it was wrong. It SHALL then appear in no report's findings. It SHALL appear in the extended report's
corrections. A report that once showed a finding that later proved false has to be answerable for it.

#### Scenario: A finding proves false

- **WHEN** a finding is withdrawn with a reason
- **THEN** the findings no longer contain it, the corrections log holds it with the date and the reason,
  and its id cannot be reused

### Requirement: The client report says plainly what was found and what is asked

The system SHALL render a client report from the ledger, containing:

- the phases and their state;
- what was received;
- the versions, with their links;
- the questions the client has to answer, from findings whose decision is still `pending`;
- the client-audience findings, grouped by level, each with its client text and its client tables;
- how the client's data is handled;
- the reference links.

It SHALL NOT contain:
- internal findings;
- internal tables;
- withdrawn findings;
- evidence blocks or queries.

A client-audience finding with no client text in the report's language SHALL stop the rendering. The
system SHALL name each such finding. It SHALL NOT fall back to the technical summary, because that
summary is not written for the client.

#### Scenario: An internal finding stays internal

- **WHEN** the ledger holds an internal finding
- **THEN** the client report does not mention it, and the extended report does

#### Scenario: A finding not yet written for the client

- **WHEN** a Spanish client report is rendered and a client finding has no Spanish text
- **THEN** no report is produced, and the finding's id is named as missing its Spanish text

### Requirement: The extended report shows everything and how to check it

The system SHALL render an extended report from the ledger, containing every finding in full:
- severity, category, audience, subject and technical summary;
- client text, if any;
- attached tables;
- evidence;
- the re-deriving query;
- the proposed action;
- the decision with its history.

It SHALL also contain the corrections log.

#### Scenario: Checking a claim

- **WHEN** a reader of the extended report doubts a figure in a finding
- **THEN** the finding shows the evidence the figure came from and the query that re-derives it

### Requirement: Reports come from the ledger and are never edited by hand

A report SHALL be produced only by rendering the ledger and its data tables. Rendering the same ledger,
tables, language and date twice SHALL produce identical reports. Each report SHALL state that it is
generated from the ledger and must not be edited.

The language SHALL be English or Spanish, chosen for the report. The labels SHALL come from the tool's
translation catalog. The client text SHALL come from the ledger in that language.

A table a finding attaches that is missing, or has no header row, SHALL stop the rendering and be named.

#### Scenario: Same input, same report

- **WHEN** the client report is rendered twice from an unchanged ledger on the same date
- **THEN** both renderings are byte-for-byte identical

#### Scenario: A missing table

- **WHEN** a finding attaches `data/crons.tsv` and the file does not exist
- **THEN** no report is produced, and the missing file is named

### Requirement: Reading the ledger needs no menu; changing it does

The following SHALL be non-interactive commands. They write nothing and print to standard output:

| Command | What it does | Exits non-zero when |
|---|---|---|
| List the findings | Shows id, severity, audience and decision | A finding is still `pending` |
| Show one finding in full | Prints every field of that finding | — |
| Validate the ledger | Checks the ledger against the schema | The ledger is invalid |
| Render a report | Prints the report to standard output, for any report kind and language | — |

Changing the ledger SHALL be a menu action that previews what it will write and asks for confirmation:
- starting a ledger;
- adding findings from a JSON file;
- recording a decision;
- setting a phase's state;
- withdrawing a finding;
- writing the reports into the environment's reports directory.

#### Scenario: Pending decisions in a script

- **WHEN** the list command is run on a ledger with findings still `pending`
- **THEN** it prints them and exits non-zero, having written nothing

### Requirement: Every reference link in the ledger can be checked

The system SHALL offer a command that requests every **reference** link in the ledger and reports each one
that does not answer with success, naming where it appears.

A reference link is one the ledger cites for a reader. It can appear in:
- the context;
- the client texts;
- the titles and notes of attached tables.

A URL inside a finding's evidence, summary or query SHALL NOT be requested. Those URLs are facts about the
client's system: its production base URL, its report server. Requesting one reaches that system, and the
first run of this check did exactly that against a client's production server.

The check needs the network. It SHALL therefore:
- run only when asked;
- never run as part of the test suite;
- write nothing.

A private source, recorded without a link, SHALL NOT count as a broken link.

#### Scenario: A URL that is evidence is never requested

- **WHEN** a finding's evidence records the client's production `web.base.url`
- **THEN** the link check does not request it, nor any URL in a summary or a query

#### Scenario: A link that moved

- **WHEN** a version's reference link answers 404
- **THEN** the check names that link and where in the ledger it appears, and exits non-zero
