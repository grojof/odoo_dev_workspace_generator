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

## 3. Reporting

- [x] 3.0 One line per step by default, keeping warnings and the tail of a failed step; `--verbose` and
      `ODWG_VERBOSE=1` stream everything. Tests.

## 3. Host

- [x] 3.1 PostgreSQL probes never prompt; an unknown role is WARN. Tests.
- [x] 3.2 `policy-rc.d` is removed via `trap`, and a leftover of the tool's own is recognised
- [x] 3.4 Coverage input through the environment; fresh runs own the checkpoint directory; gaps dropped;
      atomic checkpoint and hash writes. Tests, plus the generated driver run against stubs.
- [x] 3.5 `trust` for the development role only; the DNS rule on port 53; root downloads in
      `/var/cache/odoo_dwg`; both OpenSnitch packages checked
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
- [x] 6.3 Two fresh independent audits (docs and code). They found the coverage-check and checkpoint defects
      above, one firewall rule too wide, and doc/spec drifts — all fixed here.
- [ ] 6.4 Re-run the checks and the verifiers after the second round
