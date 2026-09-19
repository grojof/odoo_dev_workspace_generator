## Why

A generated workspace's `launch.json` only starts the Odoo server. The other everyday entry point is Odoo's
interactive shell, `odoo-bin shell`, which gives an `env` bound to a database. It is used to inspect records,
try ORM calls and debug data, and with no launch configuration developers type the command by hand and lose
the debugger.

## What Changes

- For each version, `launch.json` gains an **Odoo shell** configuration next to the server one. It runs
  `odoo-bin shell -c config/odoo<major>.conf -d <database>` in the integrated terminal under the debugger, so
  breakpoints in addons hit from the shell.
- The database is asked when the configuration starts, through a `launch.json` `inputs` prompt whose default
  is the workspace name. One prompt is shared by every version.
- The generated README mentions both configurations.
- `tools/verify_workspace_versions.py` also runs the shell on each version: an ORM query is piped in, and its
  output must come back.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `workspace-generation`: the debug launch configurations include an Odoo shell per version.

## Impact

- Code: `odoo_dwg/templates.py` (`render_vscode_launch`, README text); `tools/verify_workspace_versions.py`.
- Tests: `tests/test_templates.py`.
- Docs: `docs/workspace-layout.md`, `CHANGELOG.md`.
