# Proposal

## Why

The chain changes configuration the operator never asked to change. All of it was measured on the first
client's database:

- **Return types.** OpenUpgrade 15.0 gives each warehouse a "Returns" type and points its delivery type's
  returns at it, and its receipt type's at the delivery type, overwriting what was there. A warehouse whose
  customer returns went to its own type loses that flow.
- **Operation types created active.** OpenUpgrade 18.0 creates the multi-step reception types active on
  every active warehouse, where Odoo creates them archived for a one-step warehouse. It also fills the
  default locations 18 requires on active types only.
- **The invoice-matching rule.** OpenUpgrade 13.0 deletes Odoo's default reconciliation rule, and a
  migrated company never reloads its chart to get one back.
- **Journal mail aliases.** OpenUpgrade 13.0 recreates each journal's alias, passing its old name in an
  argument 13.0 ignores, so the alias takes the journal's name.

## What Changes

When the target is 18.0 or later:
- **At the source restore**, the driver keeps every operation type's return type, the reconciliation
  rules with their external ids, and each journal's alias name.
- **At the target step**, after the tax grids, the target's Odoo:
  - puts back each existing type's source return type;
  - archives the types the chain created that nothing but their warehouse points at;
  - gives types without default locations the ones Odoo computes, on the missing field only;
  - recreates the deleted default rule with the source's values, mapped as OpenUpgrade 15.0 maps them;
  - gives journal aliases their source names.
- Everything goes to `logs/<target>-source-configuration.tsv`. Without the kept tables the step skips it
  and says so.

## Capabilities

### Modified Capabilities

- `migration-run`: the chain keeps source configuration at the restore and puts it back at the target.

## Impact

- New `odoo_dwg/sourceconfig.py`, `odoo_dwg/templates.py`; tests in `tests/test_sourceconfig.py`.
- Docs: `docs/migration/running.md`, `CHANGELOG.md`, `docs/project/roadmap.md`.
