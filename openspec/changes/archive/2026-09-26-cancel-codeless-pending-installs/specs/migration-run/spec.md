# Spec Delta

## ADDED Requirements

### Requirement: Pending installs with no code are cancelled after the target step

When the chain crosses 18.0, the target step SHALL, last before its checkpoint, run the target's Odoo to
cancel the pending install of every module in state "to install" whose code Odoo cannot find on the
step's addons path. It SHALL leave a pending install whose code exists. It SHALL list both in
`logs/<target>-module-states.tsv`.

#### Scenario: An auto-install module whose code is gone

- **WHEN** the chain leaves an auto-install module "to install" and no addons path holds it
- **THEN** its install is cancelled and listed, and the client-modules stage does not meet it
