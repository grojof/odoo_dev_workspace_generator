# Tasks

## 1. Implementation

- [x] 1.1 Declare `setuptools_requirement` in `models.py` and use it in `plan_build_venv` and
      `render_setup_venv_sh`; keep the migration's `_setuptools_pin` behaviour unchanged
- [x] 1.2 Unit tests: the plan's pin per era, and the generated script matching the plan
- [x] 1.3 Default to the recommendation when no maximum is stated and the host is newer; explain it in the
      prompt as unproven rather than out of range; unit tests for the resolution and the prompt text

## 2. Docs

- [x] 2.1 Update `CHANGELOG.md` `[Unreleased]` (Fixed) and `docs/workspace-layout.md`

## 3. Acceptance

- [ ] 3.1 Project checks green: pytest, ruff, `openspec validate --specs`, CLI smoke
- [ ] 3.2 On this host, generate one workspace with every version from 12.0 to 19.0 using the default interpreters,
      and for each version initialise a database with `base` and serve `/web/login`; then remove the test
      workspace, its databases and filestores
