# client-intake Specification

## Purpose
Take in a copy of a client's production — its database dump, its add-ons archive and its configuration — without modifying any of it, find out exactly what the client runs, record what was found, and make that the source version a migration starts from.

## Requirements

### Requirement: The intake is recorded, and the environment follows it

A migration environment SHALL keep what its intake established in `intake.json` at the environment's root.
The record SHALL hold:
- the reference database and the read-only role;
- the client's add-on directories, in the order of the client's `addons_path`;
- the core the client runs: flavour, repository URL and commit.

Without the record, the environment SHALL behave as it does without an intake. A record the tool cannot
read SHALL be refused with its problems named, never half-used.

#### Scenario: No intake yet

- **WHEN** an environment has no `intake.json`
- **THEN** the source version is built exactly as before, from official Odoo at the branch head

### Requirement: A client dump is restored into a reference nobody modifies

The system SHALL offer an action that restores a client's custom-format dump into a database it names the
reference, and that it SHALL NOT modify afterwards: every copy the operator works on is taken from it.

The restore SHALL:
- not carry the dump's owners or grants;
- drop nothing that exists: an existing database of that name SHALL be refused;
- verify the tables and views restored against the dump's table of contents.

Every error `pg_restore` reports SHALL be classified against a declared list of known classes. Each class
states why it loses no data, and the source that shows it. An error of no known class SHALL be recorded
as a finding of high severity, never passed over. The first known class is an aggregate built on
`array_cat(anyarray)`: PostgreSQL 14 changed `array_cat` to `anycompatiblearray`, the aggregate stores no
data, and code that uses it recreates it when it runs.

#### Scenario: A dump from PostgreSQL 12 restored on 16

- **WHEN** the dump defines `CREATE AGGREGATE … (SFUNC = array_cat, STYPE = anyarray)`
- **THEN** the restore reports that one error as the known class, with its reason, and records a finding of
  low severity, and every table and view of the table of contents is present

#### Scenario: An error nobody has seen

- **WHEN** `pg_restore` reports an error matching no known class
- **THEN** the error is recorded as a finding of high severity with its text, and the action says the
  reference may be incomplete

### Requirement: A read-only role sees no secret

The system SHALL offer an action that creates a role on the reference database with these limits:
- it can connect to that database only;
- it can `SELECT` only, sequences included — reading where a sequence stands, never advancing it, because a
  wizard leaves no rows and its id sequence is the only trace that it was ever used;
- its transactions are read-only by default;
- it cannot create temporary tables;
- it cannot read a declared catalogue of secret columns: user passwords, mail and fetchmail passwords, API
  and IAP tokens, tax certificate keys and passwords, portal access tokens, `ir_config_parameter.value`,
  and attachment contents.

Tables holding a secret column SHALL be granted column by column, so that `SELECT *` on them fails rather
than leaking.

The role's password SHALL be random. It SHALL be written only to the operator's `~/.pgpass`, with mode
`600`, and SHALL never be printed.

#### Scenario: A hidden column

- **WHEN** the role selects `password` from `res_users`, or `value` from `ir_config_parameter`
- **THEN** PostgreSQL refuses it with a permission error

#### Scenario: A write, even with read-only switched off

- **WHEN** the role sets `default_transaction_read_only` off and runs an `UPDATE` in a read-write
  transaction
- **THEN** PostgreSQL refuses it with a permission error

### Requirement: The add-ons archive is classified as delivered

The system SHALL unpack a client's add-ons archive into the environment's `client-src/`, read-only, and
SHALL classify it.

**Per directory of the client's `addons_path`:**
- the git remote, branch and commit;
- commits ahead of and behind its upstream;
- files changed and not committed.

**Per module:**
- a module is a directory holding `__manifest__.py` **or** the legacy `__openerp__.py`, which Odoo up to
  12.0 still loads;
- the directory it loads from, which is the first in the client's `addons_path` order;
- duplicates, if the same module appears in more than one directory.

**Per module installed in the reference database:**
- where it loads from, or that its code is present nowhere.

**Per installed module:** the Python packages its manifest declares in
`external_dependencies['python']`. These SHALL be recorded as the source's Python dependencies, as pip
distribution names. The import name maps to the distribution name through a declared table (`OpenSSL`
is `pyOpenSSL`, `dateutil` is `python-dateutil`, …); any other import name is taken as its own
distribution name. Odoo's own `requirements.txt` does not carry them, and without them the client's
modules do not load.

Uncommitted changes, and installed modules without code, SHALL be recorded as findings.

#### Scenario: A legacy manifest

- **WHEN** an installed module's directory holds `__openerp__.py` and no `__manifest__.py`
- **THEN** the module is found, and not reported as installed without code

#### Scenario: A module needs a package Odoo's requirements do not list

- **WHEN** an installed module's manifest declares `external_dependencies = {'python': ['OpenSSL', 'zeep']}`
- **THEN** `pyOpenSSL` and `zeep` are recorded as the source's Python dependencies

#### Scenario: Production runs code the repository does not hold

- **WHEN** a directory of the archive has uncommitted changes to a module's Python and views
- **THEN** the files are listed in a finding, which says to port from the archive, not from the repository

### Requirement: The client's core is identified from history

The system SHALL identify the Odoo core the client runs:
- **the flavour:** official Odoo, OCA/OCB, or locally patched, with the files patched;
- **the exact commit**, when there is one whose tree matches.

For every core file that differs from official Odoo's branch head, the identification SHALL search the
file's content in the full history of official Odoo and of OCA/OCB at the source version, **merge commits
included**. A file whose content no commit of either ever had is a local patch.

The identification SHALL NOT use the shallow clones the environment keeps for building, because they have
no history. It SHALL read histories fetched without file contents: trees are enough to compare content
hashes.

#### Scenario: A core that is OCB

- **WHEN** every differing file of the client's core matches a version in OCB's history, and one OCB
  commit's tree matches the client's core
- **THEN** the core is identified as OCB at that commit, recorded in the intake record, and in a finding

#### Scenario: A file changed only by a merge

- **WHEN** a file's content was produced by a merge commit and by no other commit
- **THEN** it is matched, and not reported as a local patch

#### Scenario: A local patch

- **WHEN** a core file's content appears in no commit of either history
- **THEN** it is reported as a local patch, by path, in a finding of high severity

### Requirement: What the copy can act on is surveyed and recorded

The system SHALL offer an intake step that surveys the reference database, **reading only**, and records
as findings everything in it that can act on the outside world.

**Armed rules.** Each neutralisation rule with armed rows SHALL be recorded as one finding, holding:
- the rule;
- how many rows are armed;
- a sample of them;
- the severity the catalogue declares for that rule.

**Tables.** The survey SHALL also record:
- the active crons, with how overdue each one is. Every cron whose next call is already past fires at the
  first start;
- queued jobs, by channel and state;
- the outgoing mail queue, by state.

Mail that failed, and that a retry would send, SHALL be a finding of its own when there is any.

The survey SHALL connect as the database's owner: a role that cannot read secret columns cannot answer
it. If the survey cannot read something, it SHALL say "could not tell", never "clean".

#### Scenario: A production copy with crons and a tax integration armed

- **WHEN** the reference has active crons past their next call and a tax integration in production mode
- **THEN** each armed rule is a finding with its count and severity, and the crons are listed with how
  overdue each is

#### Scenario: Mail that failed for years

- **WHEN** the outgoing mail queue holds messages in the exception state
- **THEN** a finding records how many there are and the span of their dates, and says that a retry would
  send them

### Requirement: Every installed module is checked at every step, across all OCA repositories

For every installed module of Odoo or of OCA, the system SHALL record where its code is found at each step
of the chain, following the module's OpenUpgrade fate (renamed, merged, carried on). A module merged into
another needs its successor's code from the step of the merge onwards, not its own.

The code SHALL be looked for:
1. **in the core** of each step;
2. **in the OCA repositories the client uses**;
3. **in every OCA repository**, for the steps where step 2 left a gap. The list of repositories comes from
   GitHub's organisation listing.

Each OCA repository and version SHALL be read as a tree fetched without file contents, cached on the
host, and refreshed only on request. A branch that does not exist SHALL be recorded as absent, not
fetched again.

A module found at a step in no repository SHALL be a gap, recorded as a finding with the steps it is
missing from. A module found in a different OCA repository than it came from SHALL be recorded as moved.
Custom modules SHALL be listed as needing a port, not looked for.

#### Scenario: A module that moved repository

- **WHEN** an installed module lives in one OCA repository at 12.0 and in another from 14.0
- **THEN** it is found at every step, recorded as moved from 14.0, and is not a gap

#### Scenario: A module no OCA repository ports

- **WHEN** a module exists at 12.0 and in no OCA repository at 13.0 or later
- **THEN** it is a gap from 13.0, recorded in a finding that names every step it is missing from

#### Scenario: A module merged into another

- **WHEN** OpenUpgrade declares a module merged into a successor at 15.0
- **THEN** its code is looked for under its own name at 13.0 and 14.0, and under the successor's name
  from 15.0

### Requirement: The client's own code is scanned for network calls, and the scanner is shown to work

The system SHALL scan the Python code of every installed module that is neither Odoo's nor OCA's. It
SHALL look for imports and calls that reach the network or start processes. Each hit SHALL be recorded
with its file, line and pattern.

Before scanning, the system SHALL run every pattern against a declared positive control: one line each
pattern must match. If any pattern fails its control, the system SHALL refuse to report a result, rather
than report a scan that found nothing because it could find nothing.

#### Scenario: Custom code that calls out

- **WHEN** a custom module imports `requests` and calls `requests.post`
- **THEN** the hit is recorded with file, line and pattern, in a finding for that module

#### Scenario: A broken pattern

- **WHEN** a pattern no longer matches its control line
- **THEN** the step refuses to report, naming the pattern, and records no "nothing found"
