# migration-preflight Specification

## Purpose

Verifies, before a migration runs and again from inside the driver, that the host, the PostgreSQL server, the source dump and the database itself can actually carry the chain — naming exactly what is missing, including which addons directory to fill, rather than failing mid-upgrade.

## Requirements

### Requirement: Source dump integrity check

The preflight SHALL verify the supplied source dump: the file exists and is readable, and
`pg_restore --list` parses it — which also enforces the custom/tar dump format the driver requires. A
plain-SQL dump SHALL be reported as a failure with a message stating the required format.

#### Scenario: Plain SQL dump is rejected with guidance

- **WHEN** the preflight is pointed at a plain-SQL dump file
- **THEN** the dump check fails, stating that a custom-format dump (`pg_dump -Fc`) is required

### Requirement: Database-scope verification

Given a restored working database, the preflight SHALL read the actual source Odoo version from
`ir_module_module` (the `base` module's `latest_version`) and compare it against the declared source
version, and SHALL list the installed modules. A version mismatch SHALL be reported as a failure before
any migration step runs.

#### Scenario: Declared source does not match the database

- **WHEN** the environment was generated for source 13.0 but the restored database's `base` version is 12.0
- **THEN** the preflight reports the mismatch and the driver aborts before step 1

### Requirement: Per-step addons coverage

For every module installed in the database, the preflight SHALL verify that each step of the chain can find
the module somewhere that step resolves modules from:
- its `addons_path`: the per-version custom and OCA dirs, OpenUpgrade, and the target core;
- the core add-ons `odoo-bin` adds itself.

For a step up to 13.0 those are the OpenUpgrade fork's own `addons` and `odoo/addons`; no separate Odoo
clone exists.

Before reporting a module as missing, the check SHALL consult that step's OpenUpgrade checkout for the
renames and merges it declares (`openupgrade_scripts/apriori.py` from 14.0,
`odoo/addons/openupgrade_records/lib/apriori.py` in a ≤ 13 fork), and SHALL treat a module whose declared successor resolves in that step's
sources as covered.

A module that resolves nowhere and that OpenUpgrade does not account for SHALL be classified by its recorded
author:

- authored by Odoo — a core module dropped upstream. Reported as a **warning** naming the module and the
  step, and it SHALL NOT block the migration, because the upgrade itself removes it and the operator has
  nothing to supply.
- authored by anyone else — code the step genuinely needs. Reported as **blocking**, naming the module, the
  step, and the exact directory where the operator should place it.

The interactive preflight and the checks embedded in the migration driver SHALL apply the same
classification, so that the two cannot disagree about whether a chain can run.

#### Scenario: A step whose sources are not on disk is named as such

- **WHEN** coverage runs for a step whose OpenUpgrade and Odoo directories do not exist
- **THEN** it reports that the step's sources are not on disk and classifies no module, rather than
  reporting every installed module — `base` included — as dropped or missing

#### Scenario: A custom module missing for one step is pinpointed

- **WHEN** module `client_sales` is installed in the database but absent from every source of step 16.0
- **THEN** the report names `client_sales`, the step, and the `addons/odoo16/custom` directory to fill, and
  the module is in the blocking class

#### Scenario: A module OpenUpgrade renames is covered by its successor

- **WHEN** module `web_editor` is installed and step 19.0's OpenUpgrade checkout declares it renamed to
  `html_editor`, which that step's core provides
- **THEN** the module is reported as covered, not as missing, and nothing asks the operator to place it

#### Scenario: A module OpenUpgrade merges into another is covered

- **WHEN** module `web_kanban_gauge` is installed and step 17.0's OpenUpgrade checkout declares it merged
  into `web`
- **THEN** the module is reported as covered, not as missing

#### Scenario: A core module dropped upstream warns instead of blocking

- **WHEN** an Odoo-authored module is installed, resolves in no source of step 14.0, and that step's
  OpenUpgrade checkout declares neither a rename nor a merge for it
- **THEN** it is reported as a warning naming the module and the step, and the chain is still allowed to run

#### Scenario: The driver refuses only on the blocking class

- **WHEN** the driver's embedded checks find warnings but no blocking modules
- **THEN** it prints the warnings with their reason and proceeds to the first step

#### Scenario: The driver aborts when the operator's code is missing

- **WHEN** the driver's embedded checks find a module in the blocking class
- **THEN** it aborts non-zero before any migration step runs — the check reads the restored working
  database, so the restore has happened and no upgrade has — naming the module, the step and the directory
  to fill

#### Scenario: A legacy step finds core modules in the fork

- **WHEN** the chain includes the 13.0 step and the database has `base` and `web` installed
- **THEN** both resolve in the 13.0 fork (`odoo/addons` and `addons`) and neither is reported missing, in the
  interactive preflight and in the driver alike

### Requirement: Custom modules are flagged for per-version adaptation

Modules found in a step's per-version custom dir SHALL additionally be
flagged with a warning that presence is necessary but not sufficient: each target version requires the
module's code *adapted to that version's breaking changes* and, when data/schema is involved, its own
`migrations/` scripts. The report SHALL reference the staging workflow (see the `migration-staging`
capability) as the prepared path for this work.

#### Scenario: A present custom module still carries the adaptation warning

- **WHEN** module `client_sales` exists in `addons/odoo17/custom` and coverage passes for step 17.0
- **THEN** the report still lists `client_sales` as custom with a note that its 17.0 code must be adapted (e.g. view `attrs` removal) and reviewed

### Requirement: Preflight is reusable from menu and flows

The preflight SHALL be exposed as an independent migration-menu action (host scope always; database scope
when the operator names an existing database), and the same implementation SHALL back that action and the
generate flow. The migration driver runs on a host that may have no interpreter of its own, so its checks
SHALL be *rendered* from the same declared list rather than shared as code; that rendering SHALL be
confined to one place, SHALL cover every check this capability names for the driver's scope, and tests
SHALL assert that it does.

A database named by the operator MUST be a valid PostgreSQL database name before any query is built with
it; otherwise the action SHALL stop naming the value.

#### Scenario: Menu action runs without a database

- **WHEN** the operator runs the preflight from the menu without naming a database
- **THEN** the host-scope checks run and the database-scope checks are reported as skipped, not failed

#### Scenario: An invalid database name is refused

- **WHEN** the operator names `db"; DROP DATABASE x --` as the database to verify
- **THEN** the action stops naming the value, and no query runs

### Requirement: Host readiness for a native chain

The system SHALL provide a read-only migration preflight that verifies the host tools every chain needs:
`uv`, PostgreSQL reachability, the development role, and the environment's per-version addons layout —
absent `addons/odoo<major>/{custom,oca}` directories are a WARN, since a chain whose custom code has
nowhere to sit will fail a step in, not before, the migration. Because every step runs natively, no chain requires
a container runtime and the preflight SHALL NOT check for one. The result SHALL be rendered as a capability
table (check, state, detail) with states OK / WARN / MISSING / INFO, and the check MUST NOT modify the host.

#### Scenario: The same tools are checked for every chain

- **WHEN** the preflight runs for a 14 → 18 chain and for a 12 → 19 chain
- **THEN** both report `uv` and PostgreSQL, and neither reports a container runtime

#### Scenario: A missing interpreter provider is reported

- **WHEN** `uv` is absent from the host
- **THEN** the report marks it MISSING, because no step can be built without it

#### Scenario: A missing addons layout is a warning

- **WHEN** the environment's `addons/odoo<major>/{custom,oca}` directories are not on disk
- **THEN** the report marks the layout WARN and says to generate the environment again

#### Scenario: The check changes nothing

- **WHEN** the preflight runs against a host missing every prerequisite
- **THEN** it reports them and makes no change to the host

### Requirement: Decisions about modules with no successor are recorded, reused and re-checked

When a module resolves nowhere in a step and OpenUpgrade declares no successor for it, the coverage report
names it and stops there. What follows is a decision only the operator can make — the module is dropped, it
is replaced by another one, or somebody ports it — and for an official or OCA module that decision is the
same for every client migrating between the same two versions. Making it once per client is making it again
for no reason.

The system SHALL let the operator record such a decision in a file they own, keyed by the module and the
source → target pair, holding what was decided and why. Coverage SHALL apply a recorded decision to the
module it names, and SHALL report what is still **undecided** as its own class, distinct from what is
missing.

A decision SHALL NOT be believed over the sources. Each SHALL carry the evidence it was made against, and
coverage SHALL report a decision as **stale** — never apply it — when the sources now say otherwise: an OCA
module decided dead that has since been ported, a module whose successor OpenUpgrade now declares. The
fates of Odoo and OCA modules SHALL always be derived from that step's checkout and `apriori.py` at the time
the question is asked, and SHALL NOT be recorded as facts in this tool or in the operator's file.

The file SHALL be readable and writable by hand, since it is the operator's record and is carried between
clients.

#### Scenario: A decision made for one client serves the next

- **WHEN** a module dropped with no successor in 12 → 18 was decided for an earlier client, and coverage
  meets it again
- **THEN** the report shows the decision and its reason instead of asking again

#### Scenario: A decision the sources have overtaken

- **WHEN** an OCA module recorded as dead in 18.0 now resolves in that step's sources
- **THEN** coverage reports the decision as stale, naming what changed, and does not apply it

#### Scenario: What is still open is separate from what is missing

- **WHEN** coverage finds a module with no successor and no decision
- **THEN** it is reported as undecided, distinctly from a module whose code is simply not on disk

### Requirement: A rehearsal can be run against a module built to break

A chain rehearsed only against the client's own add-ons exercises the classes of change that client happens
to meet. The system SHALL be able to generate a custom add-on of its own for a chain, whose purpose is to
depend on the classes of change the chain contains and to be caught when one of them takes something away.

Each probe SHALL be derived from a record of that chain's own OpenUpgrade sources — an analysis file or
`apriori.py` — and SHALL name the record it came from. The system SHALL NOT invent a subject that the
sources do not state.

Where the chain contains no instance of a class, the system SHALL report that class as uncovered rather
than omit it silently, because a class with no probe is not a class that passed.

The generated module SHALL declare, in a table of its own, each probe's subject, the class of change, the
step the sources predict it at, and the source line it came from, verbatim.

It SHALL NOT synthesize model code referring to the subject. A reference derived wrongly fails on the
source version rather than at the step it is meant to test, and would destroy the rehearsal rather than
measure it. It SHALL declare no menu, no group and no access beyond that
table, and SHALL NOT set `auto_install`.

The system SHALL write the module only inside a migration environment.

#### Scenario: The probes come from the chain being rehearsed

- **WHEN** a tester is generated for a 12 → 16 chain whose analysis files declare `sale.order.line`'s
  `qty_delivered_manual` removed at 16.0
- **THEN** a probe names that field, that model and that step

#### Scenario: A class the chain never exercises

- **WHEN** no step of the chain removes a selection key
- **THEN** the generation reports that class as uncovered, and no probe claims to cover it

### Requirement: What a step took away is answerable per probe

The system SHALL offer an action that reports, for a chosen database, what became of each probe's subject,
by reading the database's own `ir_model` and `ir_model_fields` and the module's table. It SHALL NOT require
Odoo to run, so that a step where the module failed to load can still be reported on.

Each probe SHALL be reported as one of: still present with nothing predicted; gone as the sources
predicted; **gone with nothing predicting it**; **present where the sources predicted it would go**; or the
module's table absent altogether.

The two findings SHALL be reported first and named as findings: a subject that disappeared unannounced is
the quiet loss the run's logs do not mention, and a subject still present where a script should have
removed it is a script that did not run.

#### Scenario: A quiet removal is found

- **WHEN** a probe's field is absent from `ir_model_fields` after a step and no analysis record predicted it
- **THEN** it is reported first, as gone unannounced

#### Scenario: A migration script that did not run

- **WHEN** a probe's model is still in `ir_model` after the step whose analysis declared it obsolete
- **THEN** it is reported as still present where the sources predicted it would go

#### Scenario: The module did not install

- **WHEN** the module's own table does not exist in the database
- **THEN** the action reports that, rather than reporting every probe as intact

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
