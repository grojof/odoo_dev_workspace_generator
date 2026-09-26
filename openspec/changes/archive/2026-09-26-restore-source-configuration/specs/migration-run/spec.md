# Spec Delta

## ADDED Requirements

### Requirement: Source configuration the chain changes is put back at the target step

For a target from 18.0, the driver SHALL keep, at the source restore:
- every operation type's return type;
- the reconciliation rules, with their external ids;
- each journal's alias name.

After the tax grids and before its checkpoint, the target step SHALL run the target's Odoo to:
- put back each existing operation type's source return type, where that type still exists;
- archive each operation type the chain created that nothing but its warehouse and other created types
  points at;
- compute the default locations of the types that lack them, on the missing field only;
- recreate the source's default invoice-matching rule, when the company has no such rule, with the
  source's values and the field mapping of OpenUpgrade 15.0;
- give each journal's alias its source name.

It SHALL list everything it changed in `logs/<target>-source-configuration.tsv`. When the source checkpoint
holds no kept configuration, it SHALL skip this, say so, and record it.

#### Scenario: Returns redirected by the chain

- **WHEN** a delivery type returned to its own type in the source and the chain pointed it at a new
  "Returns" type
- **THEN** it returns to its source type again, and the unused "Returns" type is archived

#### Scenario: A resumed run from an older checkpoint

- **WHEN** the source checkpoint does not hold the kept configuration
- **THEN** the step warns, records the skip, and changes nothing
