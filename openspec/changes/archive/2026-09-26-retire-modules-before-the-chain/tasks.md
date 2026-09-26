# Tasks

## 1. Decisions

- [x] 1.1 `carry.py`: `when: before-chain` on `dropped` only; `retirement()` (modules, accepted losses,
      dependents not retired); tests in `tests/test_carry.py`.
- [x] 1.2 `decide.py` + `cli.py`: `--before-chain`, `migrate accept-loss`; tests in `tests/test_carry.py`.

## 2. The stage

- [x] 2.1 `retire.py`: the rehearsal's rules moved here, the snapshot queries, `accept`, the driver entry;
      tests in `tests/test_retire.py`.
- [x] 2.2 `templates.py`: the stage after the source restore, before `preflight_db`; tests in
      `tests/test_retire.py`.
- [x] 2.3 `tools/verify_retired_modules.py`: the comparison against a throwaway PostgreSQL (metadata,
      transient, accepted, data lost, a vanished column with values); `tools/verify_migration_driver.py`
      and `tools/verify_generated_shell.py`.

## 3. Validation and docs

- [x] 3.1 The first client: decisions and accepted losses recorded; a run from its original copy retires
      the modules and matches the prepared source.
- [x] 3.2 Docs: `docs/migration/running.md`, `docs/reference/commands.md`, `CHANGELOG.md`,
      `docs/project/roadmap.md`, `CONTRIBUTING.md`, `AGENTS.md`.
