# Tasks — add-migration-preflight

## 1. Probes & model

- [ ] 1.1 `system.py`: probes `docker_daemon_ready()` (docker info, distinguishing permission vs. absent),
      `docker_image_present(tag)`, `pg_restore_lists(dump)`, and a quoted psql scalar-query helper.
- [ ] 1.2 `models.py`: `MigrationEnv.addons_custom_dir(version)` / `addons_oca_dir(version)`
      (`addons/odoo<major>/{custom,oca}`) and `addons_path(version)` reordered custom → OCA →
      OpenUpgrade → core. Unit tests for paths and order.

## 2. Provision integration

- [ ] 2.1 `provisioning.py`: facts + rows for `uv`, docker binary, docker daemon, fallback images
      (INFO row). Pure `provision_rows` tests for the new states.
- [ ] 2.2 `planners.py`: `plan_docker_engine()` (apt `docker.io` + enable service) and
      `plan_pull_openupgrade_images(versions)`. Pure tests (command text only).
- [ ] 2.3 `workflows/provision.py`: wire both as opt-in steps of apply (same ask pattern as Node).

## 3. Preflight module

- [ ] 3.1 New `odoo_dwg/preflight.py`: `gather_host_facts(env, dump)` / `gather_db_facts(env, db)` (I/O)
      and pure `preflight_rows(...)` returning (check, state, detail) rows; chain-scoped Docker checks;
      dump format detection; version-match; per-step coverage against addons sources. Pure-row tests
      covering: native chain has no Docker rows, plain-SQL dump fails with guidance, mismatch fails,
      missing module names the step and directory, database scope "skipped" without a DB.
- [ ] 3.2 `workflows/migration.py`: "Preflight check" menu action (asks chain + optional dump path +
      optional existing DB name), renders the table; i18n strings ES.

## 4. Environment & driver integration

- [ ] 4.1 `planners.py`: migration tree creates the per-version addons dirs; `templates.py`:
      per-step conf `addons_path` includes them (order per spec). Update template/planner tests.
- [ ] 4.2 `templates.py`: `render_run_migration_sh` gains a `preflight` bash function — host checks
      before restore, DB checks (psql version query, coverage `test -d`/`test -e`) after `00_source`
      restore and before step 1, abort non-zero naming the failed check. Template tests assert every
      spec-named check appears; `bash -n` stays in WSL acceptance.
- [ ] 4.3 `workflows/migration.py`: generate flow runs host-scope preflight first, shows the table, and
      requires explicit confirmation when chain-required tools are MISSING.

## 5. Docs & bookkeeping

- [ ] 5.1 `docs/migration.md`: operator guide — pointing at the source dump (custom format), where to
      place custom/OCA addons per version (migrated branches), the preflight procedure and what each
      failure means; `docs/provisioning.md`: Docker option (docker.io decision + docker-ce alternative,
      docker group note).
- [ ] 5.2 README matrix/links if affected; CHANGELOG under [Unreleased]; i18n catalog entries; ruff +
      full test suite green; `openspec validate --specs` (after archive) green.

## 6. WSL acceptance (not automatable from Windows)

- [ ] 6.1 On OdooDevServerTest: `provision check` shows the new rows; docker.io install plan applies;
      `docker pull odoo:13.0` (and 12.0) still resolve — if delisted tags stop pulling, document plan-B
      (build from odoo/docker git tags) and mark the images row accordingly.
- [ ] 6.2 Generate a 12 → 18 env: preflight table renders; driver `bash -n`; run driver against a test
      dump far enough to see host preflight pass and DB preflight catch an intentional version mismatch.
