## 1. Model: chain & interpreter matrix (migration-environment)

- [ ] 1.1 Add `models.migration_chain(source, target)` → the ascending list of target versions after source up to target (no skips), with validation that source < target and both are in the supported range.
- [ ] 1.2 Add `models.migration_interpreter(major)` → `(python, method)`: 14/15→("3.8","uv"), 16/17→("3.10","uv"), 18/19→("3.12","uv"), 13/12→(None,"docker"); plus a `MigrationEnv` config (root, source/target, shared PG dsn, working DB name).
- [ ] 1.3 Unit-test the chain (13→18 ⇒ [14,15,16,17,18]; reject source≥target) and the matrix (≥14 native uv, 13/12 docker). Anchor the numbers to the WSL-measured uv floor.

## 2. Planners & templates (migration-environment + migration-run)

- [ ] 2.1 `planners.plan_migration_clones(env, exists)` — clone `odoo/odoo` and `OCA/OpenUpgrade` per target version on the matching branch into the shared cache, skipping present clones (`--depth 1` for the migration env).
- [ ] 2.2 `planners.plan_migration_venvs(env, exists)` — for each native version: `uv venv --python <X>`, then `uv pip install -r requirements.txt --override overrides-<ver>.txt` + `openupgradelib`; emit the per-version `overrides-<ver>.txt` (psycopg2→binary, wheel-floor lxml/Pillow/gevent/greenlet).
- [ ] 2.3 `templates.render_migration_conf(env, version)` — per-step `odoo.conf` (addons_path incl. `openupgrade_scripts`, shared PG connection, working DB).
- [ ] 2.4 `templates.render_run_migration_sh(env)` — the driver: restore source dump → working DB → initial checkpoint → per-step `odoo-bin ... --update all --stop-after-init` (≥14 loads `openupgrade_framework`; 12/13 old layout) → validate → `pg_dump` checkpoint → resume-from-last-good.
- [ ] 2.5 `templates.render_docker_step(env, version)` — the `odoo:13.0`/`odoo:12.0` `docker run` recipe against the shared PG for the Python-3.6/3.5 step (text only).
- [ ] 2.6 Unit-test: per-branch command shape (≥14 vs 13), the conf's `openupgrade_scripts` path, clone reuse, and that the driver emits a checkpoint step per version. Pure, no execution.

## 3. Workflow wiring (workflows/migration.py)

- [ ] 3.1 Implement the migration menu: generate an environment (ask source/target, build clones + venvs + configs + driver via plan → preview → apply) and print how to run the driver with a source dump.
- [ ] 3.2 Surface a clear notice when the chain includes the Odoo-13 step (Docker required) and check for `uv`/`docker` presence, pointing to `provision`/the recipe as needed. Wire the `migrate` CLI subcommand.

## 4. Docs, checks & WSL acceptance

- [ ] 4.1 Add `docs/migration.md` (frontmatter): the sequential chain, the WSL-measured interpreter table, the Docker-13 fallback, checkpointing, and official URLs (OpenUpgrade run-migration/introduction, openupgradelib, oca-port). Update README map + `CHANGELOG.md`.
- [ ] 4.2 Run `ruff check .`, `python -m pytest -q`, `openspec validate --specs`, `bash -n` on the rendered `run_migration.sh`; all green.
- [ ] 4.3 WSL acceptance: generate a small chain (e.g. 13→15), build the `uv` venvs, confirm `odoo-bin --version` for the native versions and the emitted `run_migration.sh` passes `bash -n`; record it (full data migration flagged as needing a real legacy dump).
