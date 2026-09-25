## ADDED Requirements

### Requirement: A decision can name the module that carries the old one

Besides dropping, keeping or deferring a module, the operator SHALL be able to record that it is
`renamed` to one module, or `replaced` by one or more modules, with those modules named in the decision's
`to`. Coverage SHALL settle a module with such a decision as it settles any other.

A `renamed` or `replaced` decision without `to`, or a `to` on any other kind, SHALL be reported as a
problem and SHALL NOT be applied.

A decisions file written before these kinds existed SHALL keep reading as before.

#### Scenario: A module renamed at the target

- **WHEN** a client module that resolves in no step is decided `renamed` to a module present at the target
- **THEN** coverage reports it settled with that decision, and the client-modules stage carries it

#### Scenario: A rename that names no module

- **WHEN** a decision of kind `renamed` has no `to`
- **THEN** it is reported as a problem, and nothing is renamed

### Requirement: What the client-modules stage will do is answerable before running it

`odoo-dwg migrate modules --source <version> --target <version>` SHALL print the client-modules stage's plan
from the environment's decisions and the target's sources:
- the renames, with merges shown as such;
- the modules it will update and install;
- the modules it will uninstall;
- what would stop it.

It SHALL be computed by the same logic the driver runs.

With `--database`, it SHALL also read that database:
- to name decided modules that are not installed there;
- to show a rename onto a module already installed as a merge into it.

It SHALL warn about a renamed module whose target code has no migration scripts.

It SHALL write nothing and prompt for nothing. It SHALL exit 0 when the stage can run, 1 when something
would stop it, and 2 when it could not tell.

#### Scenario: Checking a port before a run

- **WHEN** the command is run while one `to` module is missing from the target's sources
- **THEN** it names that module as blocking and exits 1, having written nothing

#### Scenario: A clean plan

- **WHEN** every decided module resolves at the target and the database has each old module installed
- **THEN** it prints the renames, installs and uninstalls, and exits 0
