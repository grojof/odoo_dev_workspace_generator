# Tasks

## 1. Implementation

- [x] 1.1 `generated_files` + `plan_workspace_links`; `plan_workspace_tree` composes them
- [x] 1.2 `plan_refresh_files` (diff, `.bak`, only changed files) and `interpreter_from_pyvenv`; unit tests
- [x] 1.3 Manage action **Refresh generated files**; **Add a version** refreshes with backups and read-back
      interpreters
- [x] 1.4 Write exactly the rendered content (no extra blank line); refresh tolerates the old trailing newline
- [x] 1.5 Complete the Spanish catalog, remove stale entries, and enforce coverage with a test

## 2. Docs

- [x] 2.1 `docs/commands.md`, `docs/workspace-layout.md`, `CHANGELOG.md`; the `run.sh` spec wording

## 3. Acceptance

- [x] 3.1 Project checks green
- [x] 3.2 On this host, through the Spanish menu:
  - refresh reports the regenerated `adv` as up to date;
  - on a throwaway workspace, with `uv` 3.8 for 14 and the host 3.12 for 18, only the stale `launch.json`
    and the hand-edited `odoo18.conf` are rewritten, the edit survives in `.bak`, and 14 stays on `uv`;
  - **Add a version** 19.0 keeps both interpreters, backs up what changes, and builds a venv that runs
    `odoo-bin --version`.
