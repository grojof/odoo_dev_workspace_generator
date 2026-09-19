## Why

When the generator improves, as it did with the `launch.json` debug configurations and the README's venv
table, an existing workspace cannot receive the new files short of deleting and regenerating it. Reviewing
the one management path that does rewrite files, **Add a version**, showed two more defects:
- It rewrote every generated file without the interpreters, so `setup_venv.sh` and the README of a workspace
  with a `uv` venv would claim the host `python3`. That is the breakage the support matrix exists to prevent.
- It overwrote hand-edited files, such as a tuned `odoo.conf`, with no copy.

Also, the heredoc that writes each file added an extra blank line, so a file on disk never equalled what the
generator renders.

## What Changes

- New management action **Refresh generated files**. It rewrites a workspace's generated files from its
  `workspace.json` (configs, run scripts, `setup_venv.sh`, `.vscode/*`, `odools.toml`, README, profile):
  - only files whose content changes are written;
  - an existing file that changes is first kept as `<file>.bak`;
  - addons, venvs, clones and databases are never touched.
- Each version's interpreter is read back from its venv's `pyvenv.cfg` (`uv` or host, and the Python
  version), so regenerated files describe and rebuild what is really there. A version without a venv gets the
  default.
- **Add a version** uses the same refresh, with backups and the read-back interpreters.
- Generated files hold exactly the rendered content. A trailing-newline-only difference from older writes
  counts as current.
- The `workspace-generation` spec names the real run scripts, `scripts/run-odoo<major>.sh`, instead of
  `scripts/run.sh`.
- Every operator-facing string has a Spanish entry, enforced by a test. Three stale catalog entries are
  removed.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `workspace-management`: refresh generated files. **Add a version** keeps interpreters and backs up the
  files it changes.
- `workspace-generation`: the tree requirement names `run-odoo<major>.sh`.

## Impact

- Code:
  - `odoo_dwg/planners.py`: `generated_files`, `plan_workspace_links`, `plan_refresh_files`, heredoc body.
  - `odoo_dwg/models.py`: `interpreter_from_pyvenv`.
  - `odoo_dwg/workflows/workspace.py`.
  - `odoo_dwg/prompts.py` and `odoo_dwg/i18n.py`.
- Tests: planners, support matrix, i18n.
- Docs: `docs/commands.md`, `docs/workspace-layout.md`, `CHANGELOG.md`.
