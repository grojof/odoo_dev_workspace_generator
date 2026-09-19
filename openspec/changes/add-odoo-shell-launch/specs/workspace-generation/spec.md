## ADDED Requirements

### Requirement: Debug launch configurations for the server and the Odoo shell

The generated `.vscode/launch.json` SHALL contain, for each configured version, two debugpy configurations
that use that version's venv interpreter and `odoo-bin`: one that starts the server with
`-c config/odoo<major>.conf`, and one that starts Odoo's interactive shell with
`shell -c config/odoo<major>.conf -d <database>`. Both SHALL run in the integrated terminal. The shell's
database SHALL be asked when the configuration starts, through a `launch.json` input whose default is the
workspace name.

#### Scenario: Server and shell per version

- **WHEN** a workspace `acme` with versions `17.0` and `18.0` is generated
- **THEN** `launch.json` has four configurations: a server and a shell for each version

#### Scenario: The shell asks for its database

- **WHEN** the Odoo 18 shell configuration is started
- **THEN** it prompts for the database, offering `acme`, and runs
  `odoo-bin shell -c <workspace>/config/odoo18.conf -d <answer>`
