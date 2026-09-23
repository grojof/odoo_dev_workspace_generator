# Tasks

## 1. Pure intake logic

- [x] 1.1 `odoo_dwg/intake.py`: `IntakeRecord` with `parse_intake`/`dump_intake` (refuses an unreadable
      record naming every problem); verify round-trip and refusal tests
- [x] 1.2 `KNOWN_RESTORE_ERRORS` (first class: `array_cat(anyarray)` aggregate on PostgreSQL 14+, with reason
      and source) and `parse_restore_errors`/`classify`; verify on a real `pg_restore` stderr shape, known
      and unknown
- [x] 1.3 `SECRET_COLUMNS` and `reader_role_sql` (column grants for tables with secrets, existence from
      `pg_attribute`); verify the SQL text, including that no `information_schema` is used
- [x] 1.4 `addons_path_dirs` (the client conf's order mapped under `client-src/`, core entries detected) and
      `classify_modules` (both manifest names, first-in-path wins, duplicates, installed-without-code);
      verify with invented fixtures, including a legacy `__openerp__.py`
- [x] 1.5 `git_blob_id`, `parse_raw_log` (tab-split, merge lines included) and `match_core` (per-file verdict,
      best commit from tree listings, client-only files apart); verify with fixtures including a file
      produced only by a merge and a local patch

## 2. Execution helpers

- [x] 2.1 `system.py`: history clone/fetch, `git log --raw` for paths, `git ls-tree` of a commit, archive
      listing/unpacking read-only; verify planners' commands in tests (no shelling out)
- [x] 2.2 `tools/verify_intake.py`: throwaway PostgreSQL (restore of a dump carrying the aggregate class and
      an unknown error, reader role refusals), throwaway git repo with a merge commit (core identification
      finds the merge-produced file and the exact commit), `git_blob_id` vs `git hash-object`, hard-linked
      filestore copy leaves the reference unchanged when the copy gains a file; verify it passes and fails
      on a mutant

## 3. Source from the intake

- [x] 3.1 `MigrationEnv.intake`, `plan_seed_environment` cloning the core pinned at its commit, source conf
      with the client's addons path and `data_dir`; verify with planner tests (with and without intake)
- [x] 3.2 `render_open_for_testing_sh`: the source case, the reference refused by name, the filestore copy by
      hard links; verify with `tools/verify_migration_driver.py` (stubs) and ShellCheck

## 4. Surface

- [x] 4.1 Migration → Take in a client copy: restore, reader role, unpack, classify, identify core, filestore,
      build source, copy to a working database — each previewed and confirmed, each writing findings,
      data tables and `intake.json`; verify with workflow tests over stubs
- [x] 4.2 Operator strings in `i18n`; verify the catalog test

## 4b. Found by starting the client's source

- [x] 4b.1 The installed modules' `external_dependencies['python']` recorded by the archive classification
      (import → pip name through a declared table), and installed into the source venv on every build;
      verify with unit tests (manifest parsing, mapping, the install command) and by starting the client's
      source on the host

## 5. Docs and gates

- [x] 5.1 `docs/migration.md` (Taking in a client copy), `docs/commands.md`, `README.md`, `CHANGELOG.md`,
      `docs/roadmap.md` (3b as the follow-up), CONTRIBUTING/CLAUDE verifier lists; verify every command shown
- [x] 5.2 Gates: pytest, ruff, openspec, `--help`, the offline verifiers, and a grep of the staged tree for
      any client name, host or real figure

## 6. On the host

- [x] 6.1 Write the first client's `intake.json` from its hand-made intake, run the new actions still missing
      (filestore, source build), and start its Odoo 12 through the guarded start on the neutralised copy,
      with the firewall and Mailpit on; read the firewall journal; record the outcome in its ledger
