# migration-preflight Specification Delta

## ADDED Requirements

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
