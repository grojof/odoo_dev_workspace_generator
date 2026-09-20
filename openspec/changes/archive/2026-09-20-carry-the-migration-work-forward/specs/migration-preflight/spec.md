# migration-preflight Specification Delta

## ADDED Requirements

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
