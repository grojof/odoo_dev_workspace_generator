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

The preflight SHALL predict the modules each step installs that the source database never had:
- the dependencies an upgraded module declares at that step and nobody installed;
- the `auto_install` modules that follow.

It SHALL follow the rule the step's own OpenUpgrade code applies, read from the checkout. Where
OpenUpgrade selects them (its 13.0 loader, its framework's `update_list` patch), every module whose
requirements are met is installed, and the patch skips localisations. Elsewhere Odoo's rule applies:
every requirement installed or about to be, and at least one about to be. A module restricted to
`countries` is not predicted. Each predicted module SHALL be listed, and checked at every later step with
the author its manifest declares, or Odoo's default when it declares none.

An installed module's dependency that no source of a step provides SHALL be a MISSING row. Where a cached
OCA tree of that version has it, the preflight SHALL name the repository.

#### Scenario: A glue module the chain installs

- **WHEN** a 13.0 step's OpenUpgrade selects an OCA glue module whose requirements the client has, and the
  module has no code at 14.0
- **THEN** the preflight lists it as installed by the chain at 13.0, and reports it missing at 14.0 before
  the run

#### Scenario: A dependency another OCA repository has

- **WHEN** a module installed at 14.0 needs, at 16.0, a module in a repository the chain did not clone
- **THEN** the preflight shows a MISSING dependency row for 16.0 and names the repository

#### Scenario: A module renamed earlier in the chain

- **WHEN** a module renamed at 13.0 depends at 14.0 on a module no source provides
- **THEN** the preflight names that dependency for 14.0, as the driver does

#### Scenario: A module missing at one step only

- **WHEN** a decision is recorded for a module with no code at 15.0 alone
- **THEN** it is applied at 15.0, and is not reported stale at the other steps

#### Scenario: A preflight after generation

- **WHEN** the preflight runs on a chain generated with twenty OCA repositories
- **THEN** it resolves the modules in those repositories without being told them again
