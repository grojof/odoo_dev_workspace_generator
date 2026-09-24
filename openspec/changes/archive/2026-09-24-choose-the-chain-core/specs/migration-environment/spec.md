# Spec Delta

## MODIFIED Requirements

### Requirement: Per-version clones from the shared cache

The system SHALL clone, for each target version in the chain, `OCA/OpenUpgrade` on the matching version
branch into the shared repo cache, and the chain's core (`odoo/odoo` or `OCA/OCB`) too from 14.0 on,
reusing an existing clone rather than re-cloning. A step up to 13.0 clones no separate Odoo: its
OpenUpgrade branch is a full Odoo fork.

The chain's source and target SHALL be validated as supported `NN.0` versions before anything is planned,
because both reach the generated driver.

#### Scenario: OpenUpgrade branch matches the Odoo version

- **WHEN** the environment is generated for a chain that includes version 16
- **THEN** the plan clones `OCA/OpenUpgrade` on branch `16.0` alongside the chain core's `16.0`, skipping any clone already present

#### Scenario: A legacy step clones only the fork

- **WHEN** the environment is generated for a chain that includes version 13
- **THEN** the plan clones `OCA/OpenUpgrade` `13.0` and no core `13.0`

#### Scenario: A source or target with shell syntax is refused

- **WHEN** the operator enters `13.0$(curl …)` or `13` as the source
- **THEN** generation stops with an invalid-version error and nothing is written

## ADDED Requirements

### Requirement: The steps run on the core the client runs, or the one the operator chooses

A migration environment SHALL have a chain core, `odoo` or `ocb`, for the steps from 14.0 on. By default
it SHALL be the core the intake identified. It SHALL be `odoo` when there is no intake or the core is
patched or unidentified. The operator MAY choose it at generation. Those steps' clone, `addons_path`,
`odoo-bin`, requirements and coverage SHALL use `<repos>/<core>-<version>`.

Generation SHALL say which core the steps use and whether it follows the client or the operator. Every
later action SHALL read the choice back from the generated step configs. It is recorded nowhere else.

#### Scenario: A client on OCB is migrated on OCB

- **WHEN** the intake identified the client's core as OCB and the operator keeps the default
- **THEN** the plan clones `OCA/OCB` for each step from 14.0 and every such step's `addons_path` names `ocb-<version>`

#### Scenario: The operator forces official Odoo

- **WHEN** the client runs OCB and the operator chooses `odoo` at generation
- **THEN** the steps use `odoo-<version>`, and a later preflight reads `odoo` back from the step configs

#### Scenario: No intake keeps official Odoo

- **WHEN** an environment has no intake and the operator keeps the default
- **THEN** every generated path is `odoo-<version>`, as before
