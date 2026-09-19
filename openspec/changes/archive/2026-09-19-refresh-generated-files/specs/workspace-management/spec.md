## ADDED Requirements

### Requirement: Refresh an existing workspace's generated files

The system SHALL offer, for an existing workspace, an action that rewrites the files the generator produces
from the workspace's `workspace.json`:
- the per-version configs and run scripts;
- `setup_venv.sh`;
- `.vscode/*`;
- `odools.toml`;
- the README;
- the profile.

Only files whose content would change SHALL be written. An existing file that changes SHALL first be copied
to `<file>.bak`. The interpreter of each version SHALL be read from its venv's `pyvenv.cfg`, so the files
describe and rebuild the venvs as they are; a version without a venv SHALL get the default interpreter. The
action SHALL NOT touch addons, venvs, clones or databases, and SHALL be previewed and confirmed. **Add a
version** SHALL write files the same way.

#### Scenario: Up-to-date workspace

- **WHEN** the refresh runs on a workspace whose generated files already match the generator
- **THEN** it reports that every generated file is up to date and plans nothing

#### Scenario: Stale and hand-edited files

- **WHEN** a workspace's `launch.json` predates the current generator and its `odoo18.conf` was edited by hand
- **THEN** the plan copies each to `.bak`, rewrites only those two files, and leaves every other file untouched

#### Scenario: Interpreters are preserved

- **WHEN** a workspace's Odoo 14 venv was built with `uv` Python 3.8 and a version is added or files are
  refreshed
- **THEN** the regenerated `setup_venv.sh` and README still build and describe Odoo 14 on `uv` Python 3.8
