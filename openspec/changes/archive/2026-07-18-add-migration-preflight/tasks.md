# Tasks — add-migration-preflight

## 1. Probes & model

- [x] 1.1 `system.py`: probes `docker_daemon_ready()` (docker info, distinguishing permission vs. absent),
      `docker_image_present(tag)`, `pg_restore_lists(dump)`, and a quoted psql scalar-query helper.
- [x] 1.2 `models.py`: `MigrationEnv.addons_custom_dir(version)` / `addons_oca_dir(version)`
      (`addons/odoo<major>/{custom,oca}`) and `addons_path(version)` reordered custom → OCA →
      OpenUpgrade → core. Unit tests for paths and order. (Also fixed: the path now threads the
      OpenUpgrade checkout ROOT so `openupgrade_framework` resolves — it previously listed the
      `openupgrade_scripts` module dir.)

## 2. Provision integration

- [x] 2.1 `provisioning.py`: facts + rows for `uv`, docker binary, docker daemon, fallback images
      (INFO row). Pure `provision_rows` tests for the new states.
- [x] 2.2 `planners.py`: `plan_docker_engine()` (apt `docker.io` + enable service) and
      `plan_pull_openupgrade_images(versions)`. Pure tests (command text only).
- [x] 2.3 `workflows/provision.py`: wire both as opt-in steps of apply (same ask pattern as Node).

## 3. Preflight module

- [x] 3.1 New `odoo_dwg/preflight.py`: `gather_host_facts(env, dump)` / `gather_db_facts(env, db)` (I/O)
      and pure `preflight_rows(...)` returning (check, state, detail) rows; chain-scoped Docker checks;
      dump format detection; version-match; per-step coverage against addons sources. Pure-row tests
      covering: native chain has no Docker rows, plain-SQL dump fails with guidance, mismatch fails,
      missing module names the step and directory, database scope "skipped" without a DB.
- [x] 3.2 `workflows/migration.py`: "Preflight check" menu action (asks chain + optional dump path +
      optional existing DB name), renders the table; i18n strings ES.

## 4. Environment & driver integration

- [x] 4.1 `planners.py`: migration tree creates the per-version addons dirs; `templates.py`:
      per-step conf `addons_path` includes them (order per spec). Update template/planner tests.
- [x] 4.2 `templates.py`: `render_run_migration_sh` gains a `preflight` bash function — host checks
      before restore, DB checks (psql version query, coverage `test -d`/`test -e`) after `00_source`
      restore and before step 1, abort non-zero naming the failed check. Template tests assert every
      spec-named check appears; `bash -n` stays in WSL acceptance.
- [x] 4.3 `workflows/migration.py`: generate flow runs host-scope preflight first, shows the table, and
      requires explicit confirmation when chain-required tools are MISSING.

## 5. Docs & bookkeeping

- [x] 5.1 `docs/migration.md`: operator guide — pointing at the source dump (custom format), where to
      place custom/OCA addons per version (migrated branches), the preflight procedure and what each
      failure means; `docs/provisioning.md`: Docker option (docker.io decision + docker-ce alternative,
      docker group note).
- [x] 5.2 README matrix/links if affected; CHANGELOG under [Unreleased]; i18n catalog entries; ruff +
      full test suite green; `openspec validate --specs` (after archive) green.

## 6. WSL acceptance (not automatable from Windows)

- [x] 6.1 On OdooDevServerTest: `provision check` shows the new rows; docker.io install plan applies;
      `docker pull odoo:13.0` (and 12.0) still resolve — if delisted tags stop pulling, document plan-B
      (build from odoo/docker git tags) and mark the images row accordingly.
      *(Done 2026-07-18: docker.io plan applied verbatim, daemon 29.1.3 up, both tags resolve via
      manifest inspect, odoo:13.0 pulled. Bonus: the probes correctly distinguished the Docker Desktop
      shim — binary present, daemon down with the shim's message as detail.)*
- [x] 6.2 Generate a 12 → 18 env: preflight table renders; driver `bash -n`; run driver against a test
      dump far enough to see host preflight pass and DB preflight catch an intentional version mismatch.
      *(Done: all three DB-preflight paths validated with synthetic -Fc dumps — version mismatch aborts;
      coverage aborts naming addons/odoo<major>/custom per step; happy path passes and chains into the
      Docker step. Two real fixes fell out: the 12/13 recipe now runs the OpenUpgrade fork's own
      odoo-bin with openupgradelib installed on the fly, and the container launches into OpenUpgrade
      code against the shared DB — semantic validation still needs a real legacy dump.)*
