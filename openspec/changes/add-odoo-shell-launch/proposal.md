## Why

A generated workspace's `launch.json` only starts the Odoo server. Three other entry points are part of daily
Odoo development, and each is typed by hand today, without the debugger:
- **Odoo's interactive shell** (`odoo-bin shell`): an `env` bound to a database, to inspect records and try
  ORM calls.
- **A server that upgrades modules on start** (`-u`): run after changing fields, views or data.
- **One module's tests** (`--test-enable --test-tags /<module>`): the place a breakpoint helps most.

## What Changes

- For each version, `launch.json` has four debugpy configurations: server, shell, upgrade modules and test
  module. All four run in the integrated terminal.
- The database, the modules to upgrade and the module to test are asked when a configuration starts, through
  `launch.json` `inputs`. The database defaults to the workspace name.
- The generated README and `docs/editor-integration.md` describe the four configurations.
- `tools/verify_workspace_versions.py` runs these configurations from the generated file, with the prompts
  answered:
  - **shell:** an ORM query is piped in and must come back.
  - **test module:** `barcodes`' tests must run and pass.
  - **upgrade modules:** the server must serve `/web/login`.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `workspace-generation`: debug launch configurations for the server, the shell, module upgrades and module
  tests.

## Impact

- Code: `odoo_dwg/templates.py` (`render_vscode_launch`, the README); `tools/verify_workspace_versions.py`.
- Tests: `tests/test_templates.py`.
- Docs: `docs/editor-integration.md`, `docs/workspace-layout.md`, `CHANGELOG.md`.
