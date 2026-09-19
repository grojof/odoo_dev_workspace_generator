# Tasks

## 1. Inputs

- [x] 1.1 Validate versions, migration source and target, OCA repositories, `db_host`, ports and Python pins.
      Validate profiles on every load. Quote paths in generated scripts. Add regression tests for each
      injection vector.
- [x] 1.2 **Add a version** applies atomically. The CLI and workflows report invalid input instead of
      crashing. Tests.

## 2. Migration

- [x] 2.1 The driver restores the newest checkpoint before the first pending step, and binds to one source
      dump by SHA-256
- [x] 2.2 Coverage and apriori come from one per-layout definition, for the preflight and the driver. Tests,
      including the legacy step.
- [x] 2.3 A migration venv is rebuilt when its interpreter changes. Tests.

## 3. Host

- [x] 3.1 PostgreSQL probes never prompt; an unknown role is WARN. Tests.
- [x] 3.2 `policy-rc.d` is removed via `trap`, and a leftover of the tool's own is recognised
- [x] 3.3 Regional Ubuntu mirrors, atomic config write, no caching of a missing apriori, the wkhtmltopdf skip
      message, staging `git` failures surfaced, stamped backups, 3.10 patch levels

## 4. Structure and cleanup

- [x] 4.1 `Command` moves to `models`; `workflows/common.py`; the apt probe moves to `system`; dead code is
      removed
- [x] 4.2 Workflow tests: loading, adding a version, interpreters read back, phrase gating, CLI errors

## 5. Docs and specs

- [x] 5.1 Fix every drift the audit listed, update SECURITY.md, and rewrite the stale spec purposes
- [x] 5.2 Update the CHANGELOG

## 6. Acceptance

- [ ] 6.1 Project checks and the four verifiers green
- [ ] 6.2 Run the generated driver with shimmed PostgreSQL tools and a failing step. Confirm that it restores
      the newest checkpoint, resumes at the failed step, and refuses a different dump. Confirm the injections
      are refused from the real menus.
- [ ] 6.3 Two fresh independent audits (docs and code) agree nothing is left for 0.2.0
