## MODIFIED Requirements

### Requirement: A decision can name the module that carries the old one

Besides dropping, keeping or deferring a module, the operator SHALL be able to record that it is
`renamed` to one module, or `replaced` by one or more modules, with those modules named in the decision's
`to`. Coverage SHALL settle a module with such a decision as it settles any other.

A `renamed` decision MAY name several modules, for a module split while porting. The first SHALL take the
old module (its record, identifiers and data, as a single rename does), and the others SHALL be installed
in the same run of the client-modules stage, under the same checks as any module the stage installs.

A `renamed` or `replaced` decision without `to`, or a `to` on any other kind, SHALL be reported as a
problem and SHALL NOT be applied.

A decisions file written before these kinds existed SHALL keep reading as before.

#### Scenario: A module renamed at the target

- **WHEN** a client module that resolves in no step is decided `renamed` to a module present at the target
- **THEN** coverage reports it settled with that decision, and the client-modules stage carries it

#### Scenario: A rename that names no module

- **WHEN** a decision of kind `renamed` has no `to`
- **THEN** it is reported as a problem, and nothing is renamed

#### Scenario: A module split in three

- **WHEN** a module is decided `renamed` to three modules
- **THEN** the stage renames it to the first and installs the other two in the same Odoo run
