# Tasks

- [x] 1.1 `models.py`: `ModuleDecision.to` (string or list, optional), read and written by
      `decisions_from_json` / `decisions_to_json`; older files read as before; tests
- [x] 1.2 `odoo_dwg/carry.py` (pure, standard library only, no package imports): the stage plan from decision
      dicts, the source → target pair, and a `read(name)` callable over the target's sources —
      renames grouped by `to`, updates, installs, uninstalls, problems (missing `to`, unreadable manifest,
      version outside the target series, `to` on the wrong kind, unknown kind, no migration scripts as a
      warning), and the database-dependent problems given the installed module set; tests
- [x] 1.3 The driver (`templates.py`): the client-modules stage after the target step, embedding
      `carry.py`'s source (read with `importlib.resources`, asserted equal in a test); pre hook, renames
      through `openupgradelib.update_module_names(merge_modules=True)` in the target's `odoo-bin shell`, one
      `odoo-bin -u … -i … --stop-after-init` without OpenUpgrade's framework, uninstalls, post hook,
      neutralise, checkpoint `<target>-modules`, step-record lines; nothing to carry writes no checkpoint;
      the resume treats the stage as a step; `--redo-modules`; tests on the rendered text
- [x] 1.4 `migrate modules` in `workflows/checks.py` and `cli.py` (`--database` and the `--db-*` options):
      the plan and its problems, exit 0/1/2; Spanish strings; tests with stubbed reads
- [x] 1.5 `migrate decide` in `cli.py`: validation shared with `carry.py`, the printed entry, `--write`
      through a temporary file and a rename, only that module's entry for the pair replaced; tests on
      `tmp_path`
- [x] 1.6 `tools/verify_migration_driver.py`: the stage against stub binaries (renames, one update/install
      run, uninstalls in that order, nothing-to-carry writes no checkpoint, `--redo-modules` restores the
      target checkpoint and runs only the stage, a missing `to` stops before any database command)
- [ ] 2.1 On the first client's environment (by hand, nothing enters the repository): regenerate the
      driver, record the decisions with `migrate decide`, check them with `migrate modules`, and run the
      stage on the migrated database with the first ported module; then `--redo-modules`
- [x] 2.2 Docs: `docs/migration/running.md`, `docs/reference/commands.md`, `README.md`,
      `CHANGELOG.md`, `docs/project/roadmap.md`
