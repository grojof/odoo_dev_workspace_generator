# migration-environment Specification (delta)

## ADDED Requirements

### Requirement: Per-version custom and OCA addons layout

The migration environment SHALL define, for each target version in the chain, `addons/odoo<major>/custom`
and `addons/odoo<major>/oca` directories under the environment root, create them during generation, and
thread them into that step's `addons_path` ahead of OpenUpgrade and core (operator code takes precedence in
module lookup). The generated documentation SHALL state that the operator places each module's *migrated
branch* for that version there.

#### Scenario: Step config includes the per-version addons dirs

- **WHEN** the per-step config for version 16 is rendered
- **THEN** its `addons_path` lists `addons/odoo16/custom` and `addons/odoo16/oca` before the OpenUpgrade and core entries

### Requirement: Generation runs the host preflight first

`Generate a migration environment` SHALL run the chain-scoped host preflight before planning and show its
table. MISSING chain-required tools SHALL NOT hard-block generation (the plan itself may be unaffected) but
SHALL require an explicit confirmation to continue.

#### Scenario: Missing Docker prompts before generating a 12-chain

- **WHEN** the operator generates a 12 → 18 environment on a host without Docker
- **THEN** the preflight table shows Docker MISSING and generation continues only after the operator confirms
