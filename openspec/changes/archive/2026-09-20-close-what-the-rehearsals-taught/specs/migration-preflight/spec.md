# migration-preflight Specification Delta

## MODIFIED Requirements

### Requirement: What a step took away is answerable per probe

The system SHALL offer an action that reports, for a chosen database, what became of each probe's subject,
by reading the database's own `ir_model`, `ir_model_fields` and `ir_module_module` and the module's table.
It SHALL NOT require Odoo to run, so that a step where the module failed to load can still be reported on.

**A probe SHALL report a loss only where there was something to lose.** A field whose owning model is not
in the database, and a module whose subject *and* declared successor are both absent, were never there:
the probe measured nothing and SHALL say so rather than report the chain behaving.

**A probe SHALL be judged against its own step.** Its claim is about the step that changed the subject, and
the database it is read from may be anywhere in the chain. Where the database is *past* that step, a
missing subject SHALL NOT be reported as a finding, because a later step may have removed it. Where the
database has *not reached* that step, the subject's presence SHALL NOT be reported as a finding, because
nothing has happened to it yet. A subject the sources predicted would go is judged from any later version,
since "gone from its step onward" holds there too.

Each probe SHALL be reported as one of: still present with nothing predicted; gone as the sources
predicted; **gone with nothing predicting it**; **present where the sources predicted it would go**; not
reached yet; past its step; nothing observed; or the module's table absent altogether.

Only the two emphasised states are findings. They SHALL be reported first and named as findings: a subject
that disappeared unannounced is the quiet loss the run's logs do not mention, and a subject still present
where a script should have removed it is a script that did not run. The states that measured nothing SHALL
sort last, after everything that was measured, so that they cannot be read as passes.

#### Scenario: A quiet removal is found

- **WHEN** a probe's field is absent from `ir_model_fields` after its own step, its model is present, and no
  analysis record predicted the field would go
- **THEN** it is reported first, as gone unannounced

#### Scenario: A migration script that did not run

- **WHEN** a probe's model is still in `ir_model` after the step whose analysis declared it obsolete
- **THEN** it is reported as still present where the sources predicted it would go

#### Scenario: A subject that was never in this database

- **WHEN** a probe names a field whose model this database does not have, or a module whose successor is
  absent too
- **THEN** it is reported as having measured nothing, and is not counted as the chain behaving

#### Scenario: A database read past the probe's step

- **WHEN** a probe about step 15.0 is read from a database already at 19.0 and its subject is missing
- **THEN** it is not reported as a finding, because a later step may have removed it

#### Scenario: The module did not install

- **WHEN** the module's own table does not exist in the database
- **THEN** the action reports that, rather than reporting every probe as intact

## ADDED Requirements

### Requirement: A module's dependencies must resolve, not only the module

A module resolving is not the same as a step running. Odoo refuses to upgrade a module whose manifest names
a dependency it cannot find, so coverage answering "everything resolves" was not the same as the step
succeeding.

The system SHALL check, for every module that resolves in a step's sources, that each dependency its
manifest declares also resolves there, and SHALL report the module and the dependencies that do not. The
manifest SHALL be parsed, never executed.

A manifest that cannot be read SHALL name no dependency, rather than fail the check: it is a checkout's
file and may hold anything.

#### Scenario: A dependency in a repository nobody cloned

- **WHEN** a module resolves but its manifest names a module that resolves in no source of that step
- **THEN** both are named, before any step runs

#### Scenario: A manifest that cannot be parsed

- **WHEN** a module's manifest is not readable as a literal
- **THEN** the check reports no dependency for it and does not fail
