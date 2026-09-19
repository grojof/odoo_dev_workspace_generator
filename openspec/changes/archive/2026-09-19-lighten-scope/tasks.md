# Tasks

## 1. Shallow workspace clones

- [x] 1.1 Clone Odoo and OCA repositories with `--depth 1 --branch <v> --single-branch` in
      `plan_repo_cache`; verify unit tests assert the flag for both kinds of clone and that an existing clone
      is still skipped
- [x] 1.2 Document `git -C <clone> fetch --unshallow` in `docs/workspace-layout.md` and the generated
      per-workspace README

## 2. Ubuntu 24.04 only, Python 3.12 floor

- [x] 2.1 Drop the 22.04 row from `SUPPORTED_HOSTS` and raise `TOOL_PYTHON_MINIMUM` to 3.12; set
      `requires-python = ">=3.12"`, drop the 3.10 classifier, move ruff to `target-version = "py312"`, and fix
      (not suppress) whatever it newly reports; verify the floor test still ties the three together
- [x] 2.2 Remove the wkhtmltopdf assets for hosts that are no longer accepted, keeping `noble`; verify the
      provisioning tests
- [x] 2.3 Update the tests that relied on 22.04 or on 3.10 (host-release rows, `tomllib` without
      `importorskip`)
- [x] 2.4 Update `docs/support-matrix.md`, `README.md`, `docs/wsl-setup.md`, `docs/provisioning.md`,
      `CONTRIBUTING.md` and `CLAUDE.md`: one host, a 3.12 floor, no separate 3.10 run; verify with grep that
      no statement of 22.04 support or a 3.10 floor survives

## 3. Dropped items and manual checks

- [x] 3.1 Delete `openspec/changes/add-ai-emitters/` and remove the promise of AI emitters from the principle
      in `CLAUDE.md`
- [x] 3.2 Document loopback `trust` as intentional in `docs/provisioning.md`, with the manual steps for
      password authentication
- [x] 3.3 Rewrite `docs/roadmap.md`: record both drops with their reasons, fold the `launch.json` and
      status-bar items into one manual VSCode check, correct the clone-size figure, keep the "OdooLS 1.5
      stable" review line
- [x] 3.4 Update `CHANGELOG.md` `[Unreleased]`

## 4. Acceptance

- [x] 4.1 Run the project checks green: `python -m pytest -q`, `python -m ruff check .`,
      `openspec validate --specs`, `python -m odoo_dwg --help`, and both verifiers
- [x] 4.2 Generate a workspace from an empty cache on this host and confirm the clone is shallow and sized as
      measured, then run the refresh action and confirm it advances the clone
