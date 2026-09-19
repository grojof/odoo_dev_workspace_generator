## ADDED Requirements

### Requirement: Debug launch configurations for everyday development

The generated `.vscode/launch.json` SHALL contain four debugpy configurations for each configured version.
All of them SHALL use that version's venv interpreter and `odoo-bin`, run in the integrated terminal and set
`justMyCode` off:
- **server:** `-c config/odoo<major>.conf`;
- **shell:** `shell -c config/odoo<major>.conf -d <database>`, Odoo's interactive shell;
- **upgrade modules:** `-c config/odoo<major>.conf -d <database> -u <modules>`, which keeps serving after the
  upgrade;
- **test module:** `-c config/odoo<major>.conf -d <database> -u <module> --test-enable --test-tags /<module>
  --stop-after-init`.

The database, the modules and the test module SHALL be asked when a configuration starts, through
`launch.json` inputs. The database input SHALL default to the workspace name.

#### Scenario: Four configurations per version

- **WHEN** a workspace `acme` with versions `17.0` and `18.0` is generated
- **THEN** `launch.json` has eight configurations: server, shell, upgrade modules and test module for each
  version

#### Scenario: The shell asks for its database

- **WHEN** the Odoo 18 shell configuration is started
- **THEN** it prompts for the database, offering `acme`, and runs
  `odoo-bin shell -c <workspace>/config/odoo18.conf -d <answer>`

#### Scenario: Testing one module

- **WHEN** the Odoo 18 test module configuration is started and `sale` is entered as the module
- **THEN** it upgrades `sale`, runs only the tests tagged `/sale` and stops
