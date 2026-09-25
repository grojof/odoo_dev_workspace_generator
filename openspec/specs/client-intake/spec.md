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

### Requirement: Uninstalling modules is rehearsed on a throwaway copy and compared table by table

The system SHALL offer an intake step that shows, on the client's own data, what uninstalling a set of
modules deletes. It SHALL take:
- a working copy of the reference;
- the modules to uninstall.

It SHALL refuse, before any plan:
- the reference database;
- a copy that is not neutralised (the neutralisation check finds something armed, or the mail can leave);
- a module that is not installed in the copy;
- a throwaway database name that already exists.

Before any plan, the step SHALL name every installed module that depends on those asked for, directly or
not, because the uninstall takes each of them along. The first real intake reasoned from what each module
owned and missed a client module that depended on one of them.

**The rehearsal.** One previewed plan, confirmed with a phrase:
1. The working copy SHALL be cloned to a throwaway database. The working copy itself SHALL NOT be
   modified.
2. The throwaway database SHALL get its own filestore, hard-linked to the reference's, as a copy opened
   for testing does.
3. The modules SHALL be uninstalled there by the source version's own Odoo (the client's core, its
   add-ons, its interpreter), with no HTTP service and no cron thread.
4. The throwaway database SHALL be neutralised again and checked, because an uninstall reloads the
   registry and can write crons.

**The comparison.** Both databases SHALL be read, and for every table of the working copy the step SHALL
record the exact row count before and after, and every column that is gone. Each difference SHALL be named
as one of:
- **module data:** rows the uninstalled modules owned through `ir_model_data`, which a reinstall loads
  again;
- **wizard:** the table of a transient model;
- **metadata:** the registry's own tables (`ir_model*`, `ir_ui_*`, actions, access rules, translations);
- **recomputed:** a dropped column of a related field, filled again by a reinstall;
- **data lost:** anything else — rows beyond what the modules owned, or a dropped column that held values.
  For a dropped column, the number of rows that held a value SHALL be read from the working copy; `false`
  and the empty string are how Odoo stores "unset", and SHALL NOT count as values.

A many2many table named after a transient model's table SHALL count as wizard. The tool's own record
(`odwg_*` tables), which the re-neutralisation writes to, SHALL count as metadata.

The modules the uninstall took along, beyond the ones asked, SHALL be named.

The step SHALL record the comparison as a data table, and one finding: `high` when any client data is
lost, naming the tables and columns; otherwise `info`, stating that no client data was lost and how many
rows of each other kind went. If it cannot read either database, it SHALL say it could not tell, and SHALL
record nothing.

The throwaway database SHALL be left in place for inspection, and the step SHALL say so.

#### Scenario: A module that owns only its own configuration

- **WHEN** the rehearsal uninstalls a module whose only rows are its own export templates
- **THEN** those rows are named module data, and the finding is `info`

#### Scenario: A dropped column that held values

- **WHEN** an uninstalled module's stored, non-related field held values in 3 rows
- **THEN** the column is named data lost with 3 rows, and the finding is `high`

#### Scenario: A dependent module goes too

- **WHEN** an installed module depends, directly or through another, on one asked for
- **THEN** it is named before the plan, and again among the modules the uninstall took along

#### Scenario: A value Odoo stores for "unset"

- **WHEN** a dropped boolean column is `false` on every row
- **THEN** it is named empty, not data lost

#### Scenario: A copy that is not neutralised

- **WHEN** the working copy has an active cron outside housekeeping
- **THEN** the step refuses before any plan, and names the neutralise action

### Requirement: The client's own modules are audited from their data

The system SHALL offer an intake step that audits every installed module the intake classified as the
client's own, reading the reference only. The operator MAY name other modules. For each module it SHALL
record:
- the installed modules that depend on it;
- each model it created, with its rows and the rows written since a date the operator gives. For a
  transient model, instead, the times it was opened, read from its id sequence;
- each stored field it created, with the rows holding a value and the rows written since the date with a
  value, and the last such write. `false` and the empty string SHALL NOT count as values. A related field
  SHALL be marked recomputed;
- each many2many table it created, with its rows;
- each document (report action) it declares, with:
  - its model;
  - whether it is in the Print menu;
  - whether it is registered under another module's namespace;
  - the attachments named as it names its PDF, in total and since the date;
- whether OCA publishes a module of the same name, from the cached OCA trees.

A module SHALL be labelled from that evidence:
- *no data* when nothing it created holds a value or a row, and no wizard of it was ever opened;
- *not used since <date>* when it holds data but none was written since the date and no print of its
  documents was counted since it;
- otherwise *in use*.

The label is evidence for the operator's decision, not the decision.

Given a migrated database, the step SHALL also record, for every field and table, whether it exists there
and holds the same number of values.

Given a web access log (Odoo's own or a proxy's), the step SHALL count, per document, the requests to
`/report/<pdf|html>/<document>/` since the date. A print is not recorded anywhere else: Odoo stores no row
for it, and a production log at `log_level = warn` sets `werkzeug:WARNING` and records no request.

The step SHALL record the table and one finding. If it cannot read the reference, it SHALL say it could
not tell, and record nothing.

#### Scenario: A field used last in 2022

- **WHEN** a module's only field holds a value on one row, last written in 2022, and the date is 2025-01-01
- **THEN** the module is labelled not used since 2025-01-01

#### Scenario: A document printed through the proxy

- **WHEN** the access log holds three `GET /report/pdf/acme_reports.invoice/42` requests since the date
- **THEN** that document's prints are three, and its module is in use

#### Scenario: A document under another module's namespace

- **WHEN** a client module declares its report action as `account.report_acme_invoice`
- **THEN** the audit flags it, because updating `account` in the chain can remove or overwrite it

### Requirement: Bank statement lines imported twice are found from the bank's own balances

For a source up to 13.0, the system SHALL offer an intake step that reads the reference only and finds
the bank statement lines imported more than once. It SHALL treat as proven only:
- statements whose opening balance plus their lines equals their closing balance;
- a day that two or more such statements of the same journal hold with identical content (journal, date,
  amount, label, reference, note and partner name of every line) and the same end-of-day balance.

Within such a day, each movement SHALL be its line content plus its occurrence index, so two identical
movements inside one day are two movements. Of each movement's copies, one SHALL be kept: a reconciled one
if any, else the lowest id.

The step SHALL record:
- each other unreconciled copy, as a duplicate with the line it duplicates;
- each other reconciled copy, as a movement reconciled more than once;
- how many statements match their file;
- how many unreconciled lines remain, and how many fall after the company's lock date.

It SHALL write the table, a SQL file that deletes a listed line only while it has no journal item and its
kept twin still exists with the same content, and one finding. It SHALL delete nothing itself. A source
from 14.0, or a reference it cannot read, SHALL be refused with the reason, and nothing recorded.

#### Scenario: A bank day imported twice

- **WHEN** two statements of one journal that match their files both hold 3 March with the same lines and the same end-of-day balance, and one copy's lines are reconciled
- **THEN** the other copy's unreconciled lines are listed as duplicates of the reconciled ones

#### Scenario: Two equal fees on one day are not a duplicate

- **WHEN** one statement holds two identical 1.50 fee lines on the same day and no other statement holds that day
- **THEN** neither line is listed

#### Scenario: A movement reconciled in both copies

- **WHEN** a day imported twice has the same movement reconciled in both statements
- **THEN** it is recorded as reconciled more than once, and not in the SQL file

#### Scenario: A statement that does not match its file proves nothing

- **WHEN** a statement's lines do not add up to its closing balance
- **THEN** none of its days is used as proof

### Requirement: Journal codes the target refuses are found and renamed before the chain

The system SHALL offer an intake step that reads the reference only and finds, per company, the journals
that share a code, and those whose codes differ only by case or surrounding spaces. In each group the
journal with most entries SHALL keep its code, the lowest id on a tie. Every other journal SHALL get a
proposed code of 1 to 5 letters or digits, unique in its company.

The step SHALL write a table the operator may edit. On a later run it SHALL keep the codes the operator
wrote there, and refuse, naming them, codes that are not 1 to 5 letters or digits or not unique in the
company. It SHALL write a SQL file that changes a journal's code only while the journal still has its old
code and no journal of its company has the new one, and one finding. It SHALL change nothing itself.

#### Scenario: Two journals share a code

- **WHEN** journals 101 (900 entries) and 102 (40 entries) of one company both have code `BANK1`
- **THEN** 101 keeps `BANK1`, 102 gets a proposed code unused in the company, and the SQL renames 102 only

#### Scenario: Codes that differ only by a space

- **WHEN** one journal has `CASH` and another `CASH `
- **THEN** they are one confusable group, and the one with fewer entries gets a proposal

#### Scenario: The operator's code is kept, a bad one refused

- **WHEN** the operator writes `ACME1` for journal 102 in the table and re-runs the step
- **THEN** the SQL uses `ACME1`, and a code such as `AC ME` or one already used in the company stops the step with its name

#### Scenario: The constraint is added after the SQL

- **WHEN** the SQL has run on a copy
- **THEN** `unique (company_id, code)` can be added to `account_journal`, and running the SQL again changes nothing

### Requirement: Unreconciled bank lines of closed periods can be left behind, on the accountant's decision

The bank statement step SHALL also list, for a source up to 13.0, the unreconciled lines dated on or
before the later of their company's fiscal-year and period lock dates, other than the certain duplicates.
A line whose exact amount matches an open receivable or payable item of the same partner SHALL be kept
and listed apart. The others SHALL be listed with journal, date, amount, label, reference, partner, note and
statement, as the file to deliver.

The step SHALL write a separate SQL file that deletes a listed line only while no journal item points at
it and its date is still on or before its company's lock date. It SHALL change nothing itself, and its
finding SHALL say that applying the file is the client's accountant's decision.

#### Scenario: A closed-period line with no match is listed to leave behind

- **WHEN** the lock date is 31 July and an unreconciled line of 3 March matches no open item
- **THEN** it is in the table and in the SQL

#### Scenario: A closed-period line matching an open invoice is kept

- **WHEN** an unreconciled line of 3 March has the exact amount of an open invoice of the same partner
- **THEN** it is listed as kept and is not in the SQL

#### Scenario: A line after the lock date is ongoing work

- **WHEN** an unreconciled line is dated after the lock date
- **THEN** it is in neither the table nor the SQL

### Requirement: The operator may give any journal a readable code

The journal codes step SHALL accept, in the table it writes and reads back, a code for any journal of the
company: journals outside every group, and the journal that keeps a group's code, included. A journal
outside every group that the operator renames SHALL appear in the plan as renamed by the operator. A code
equal to the journal's current code SHALL rename nothing. A new code that is another journal's current
code SHALL be refused, naming both journals. Codes SHALL still be 1 to 5 letters or digits and unique in
the company once every rename applies. The SQL SHALL be guarded as for the other renames.

#### Scenario: A journal with a unique but unclear code

- **WHEN** the operator writes `BAN01` for a journal whose code `BNK1` no other journal shares
- **THEN** the plan renames it as the operator's, and the SQL renames it while it still has `BNK1` and `BAN01` is free

#### Scenario: The journal that keeps a group's code gets a readable one

- **WHEN** the operator writes `ESB01` for the journal that would keep the shared `BANK1`
- **THEN** it is renamed to `ESB01`, and the others of the group get their own codes

#### Scenario: A chained rename is refused

- **WHEN** the operator gives journal A the current code of journal B
- **THEN** the step stops and names both journals
