# Proposal

## Why

OpenUpgrade 18.0 patches `update_list` to mark "to install" every uninstalled auto-install module whose
recorded dependencies are installed, whether or not its code still exists. Dependencies merged or renamed
along the chain make old auto-install modules look satisfied. Odoo skips them as not installable and ends
the step with "Some modules have inconsistent states". Every later module operation repeats that error,
including the client-modules stage, and the Apps screen shows installs that can never happen. The first
client had five.

## What Changes

When the chain crosses 18.0, the target step runs the target's Odoo last before its checkpoint. It cancels
the pending install of each module whose code Odoo cannot find (`get_module_path`), with
`button_install_cancel`, as the Apps screen does. A pending install whose code exists is left for the
operator. Both are listed in `logs/<target>-module-states.tsv`.

## Capabilities

### Modified Capabilities

- `migration-run`: the target step cancels pending installs with no code.

## Impact

- New `odoo_dwg/modulestates.py`, `odoo_dwg/templates.py`; tests in `tests/test_modulestates.py`.
- Docs: `docs/migration/running.md`, `CHANGELOG.md`, `docs/project/roadmap.md`.
