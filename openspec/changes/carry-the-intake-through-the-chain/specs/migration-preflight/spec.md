# Spec Delta

## ADDED Requirements

### Requirement: The preflight and the driver answer coverage the same way

Every action after generation SHALL read back the OCA repositories the chain linked, from each step's
`addons/odoo<major>/oca` directory. Without them, a module a step loads from its repository's directory
reads as missing.

The preflight SHALL check a module's dependencies under the name the step knows it by, after the renames
of earlier steps, as the driver does.

A recorded decision SHALL be reported stale only when no step of the chain needs it. That the module
resolves at another step is expected: the decision is about the steps where it does not.

#### Scenario: A module renamed earlier in the chain

- **WHEN** a module renamed at 13.0 depends at 14.0 on a module no source provides
- **THEN** the preflight names that dependency for 14.0, as the driver does

#### Scenario: A module missing at one step only

- **WHEN** a decision is recorded for a module with no code at 15.0 alone
- **THEN** it is applied at 15.0, and is not reported stale at the other steps

#### Scenario: A preflight after generation

- **WHEN** the preflight runs on a chain generated with twenty OCA repositories
- **THEN** it resolves the modules in those repositories without being told them again
