# Spec Delta

## ADDED Requirements

### Requirement: Editor configuration for the official Odoo language server

The system SHALL write an `odools.toml` at the workspace root holding one `[[config]]` profile per Odoo
version in the workspace. Each profile SHALL set only `name`, `odoo_path`, `addons_paths` and
`python_path`, as absolute paths: `odoo_path` pointing at that version's clone in the shared cache,
`addons_paths` at the workspace's own custom and OCA add-on directories for that version, and `python_path`
at that version's virtualenv interpreter. The file SHALL NOT use template variables, profile inheritance or
options the language server documents as version-specific, so that it stays valid across its releases.

The workspace SHALL recommend the official `Odoo.odoo` extension, and SHALL NOT recommend a third-party Odoo
extension in its place. The workspace settings SHALL turn the Python extension's own language server off, so
that Python sources are analysed by one server only.

The system SHALL NOT generate a `jsconfig.json`: JavaScript and OWL support comes from the language server
itself, reading the manifests' asset bundles.

#### Scenario: One profile per version with the documented minimal keys

- **WHEN** a workspace `acme` with versions `17.0` and `18.0` is generated
- **THEN** its `odools.toml` holds two `[[config]]` profiles, each setting exactly `name`, `odoo_path`,
  `addons_paths` and `python_path`, with `odoo_path` at that version's shared clone and `python_path` at
  `.venv/odoo<major>/bin/python`

#### Scenario: Paths are absolute and free of template variables

- **WHEN** the `odools.toml` of any workspace is rendered
- **THEN** every path is absolute and no `${...}` or `$...` template token appears in it

#### Scenario: Core add-ons come from the Odoo path, not the add-on list

- **WHEN** the profile for version `18.0` is rendered
- **THEN** its `addons_paths` lists the workspace's custom and OCA directories for 18.0 and does not repeat
  the clone's own `addons` directory, which the language server loads from `odoo_path`

#### Scenario: The official extension is recommended

- **WHEN** `.vscode/extensions.json` is rendered
- **THEN** it recommends `Odoo.odoo` and does not recommend `trinhanhngoc.vscode-odoo`

#### Scenario: One Python analyser, not two

- **WHEN** `.vscode/settings.json` is rendered
- **THEN** it sets `python.languageServer` to `None`

#### Scenario: No jsconfig is generated

- **WHEN** a workspace is generated
- **THEN** the plan writes no `jsconfig.json`
