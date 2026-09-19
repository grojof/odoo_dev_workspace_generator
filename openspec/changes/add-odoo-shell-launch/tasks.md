# Tasks

## 1. Implementation

- [x] 1.1 Emit server, shell, upgrade-modules and test-module configurations per version with `odooDatabase`,
      `odooModules` and `odooTestModule` inputs in `launch.json`; unit tests for names, arguments and inputs
- [x] 1.2 Describe the four configurations in the generated README
- [x] 1.3 Make `tools/verify_workspace_versions.py` run the generated configurations: shell (piped ORM query),
      test module (`barcodes`) and upgrade modules (`/web/login`)

## 2. Docs

- [x] 2.1 Update `docs/editor-integration.md`, `docs/workspace-layout.md` and `CHANGELOG.md`

## 3. Acceptance

- [x] 3.1 Project checks green: pytest, ruff, `openspec validate --specs`, CLI smoke
- [x] 3.2 Run `tools/verify_workspace_versions.py` on this host: every version from 12.0 to 19.0 passes all
      four configurations
