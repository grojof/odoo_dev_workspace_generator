# migration-environment Specification Delta

## ADDED Requirements

### Requirement: A migration environment may name OCA repositories

`addons/odoo<major>/oca` is created empty for the operator to fill by hand, so whether an OCA module is
ported to a step's version cannot be derived — only guessed, by whoever last copied something in. That is a
derivable fact answered by hand, and a hand answer about someone else's code ages without saying so.

A migration environment SHALL accept a list of OCA repositories, validated as the workspace surface
validates them. Generation SHALL clone each one per chain version into the shared cache and link it under
that step's `addons/odoo<major>/oca`, exactly as the workspace surface does, so a step resolves an OCA
module from the branch that OCA publishes for that version.

A repository with no branch for a version SHALL be reported for that step and SHALL NOT fail the
generation: a module OCA has not ported is a fact the operator needs, not a reason to refuse to build the
environment. An environment naming no repositories SHALL behave exactly as one does today.

#### Scenario: An OCA module resolves from its own version branch

- **WHEN** an environment names `server-tools` and is generated for a 12 → 18 chain
- **THEN** each step's `addons/odoo<major>/oca` links that repository's branch for that version, and
  coverage resolves its modules from there

#### Scenario: A repository not ported to a version is named, not fatal

- **WHEN** a named repository has no branch for 18.0
- **THEN** generation reports that step as having no OCA source for it and completes
