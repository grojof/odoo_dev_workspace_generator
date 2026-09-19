## MODIFIED Requirements

### Requirement: Per-client workspace tree

The system SHALL generate, under `<base>/<name>/`:
- the directories `addons-custom/` and `addons-oca/`, the latter holding symlinks into the shared OCA cache;
- a `config/odoo<major>.conf` per version;
- a `scripts/` directory with `setup_venv.sh` and one `run-odoo<major>.sh` per version;
- a `<name>.code-workspace` file;
- a `.vscode/` directory (`tasks.json`, `launch.json`, `settings.json`, `extensions.json`);
- a per-workspace `README.md`.

All generated files SHALL be English text and SHALL hold exactly the rendered content.

#### Scenario: Full tree is planned

- **WHEN** a workspace `acme` with version `18.0` is generated
- **THEN** the plan creates `addons-custom/`, `addons-oca/`, `config/odoo18.conf`, `scripts/setup_venv.sh`,
  `scripts/run-odoo18.sh`, `acme.code-workspace`, `.vscode/*`, and `README.md`

#### Scenario: Rendered odoo.conf carries the composed addons_path and derived port

- **WHEN** `config/odoo18.conf` is rendered for workspace `acme`
- **THEN** it contains an `addons_path` composed of custom + OCA + shared `odoo/addons` and the derived
  `http_port` for that version
