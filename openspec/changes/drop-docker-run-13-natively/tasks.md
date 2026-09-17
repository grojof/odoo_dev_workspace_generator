# Tasks

## 1. Every step is native

- [ ] 1.1 In `models.py`, make Odoo 12 and 13 `uv`-acquired with 3.8 as their recommended interpreter, drop
      the Docker acquisition method and `needs_docker()`; verify unit tests assert `migration_interpreter`
      returns `("3.8", "uv")` for 13 and that no version maps to a container
- [ ] 1.2 Give `MigrationEnv` an add-ons path for the ≤ 13 layout (custom, OCA, the OpenUpgrade checkout's
      own `addons`) instead of the ≥ 14 composition that points at a never-cloned `odoo-13.0`; verify a unit
      test asserts the 13 path contains the fork's `addons` and no `odoo-13.0` directory
- [ ] 1.3 Verify `is_native` is true for every version in every supported chain, and delete the branches that
      existed only for the container case

## 2. Build constraints

- [ ] 2.1 Add `constraints_file(version)` to `MigrationEnv` and `render_migration_constraints(version)` to
      `templates.py`, emitting `setuptools<58` for 13.0 and nothing for versions that need no build repair;
      verify unit tests cover both
- [ ] 2.2 Write the constraints file in `plan_migration_venvs` and pass `--build-constraints` on the
      requirements install only where a file exists; verify a unit test asserts the flag appears for 13.0 and
      not for 18.0

## 3. The ≤ 13 step shape

- [ ] 3.1 Emit a `conf/odoo13.conf` like the other steps, with the ≤ 13 add-ons path; verify a unit test
      asserts it names the fork's `addons` directory
- [ ] 3.2 Render the ≤ 13 step as a native `odoo-bin` run from its venv with an explicit `--addons-path` and
      without `--upgrade-path` / `--load`; verify a unit test asserts the emitted step contains
      `--addons-path`, contains neither flag, and that no `docker run` appears anywhere in the driver
- [ ] 3.3 Verify the regenerated driver passes `bash -n`

## 4. Docker leaves

- [ ] 4.1 Remove the Docker rows, facts and probes from `preflight.py` and its driver-embedded host checks;
      verify unit tests assert no chain produces a Docker row
- [ ] 4.2 Remove the Docker rows and facts from `provisioning.py` and the Docker probes from `system.py`;
      verify the provisioning tests cover the reduced table
- [ ] 4.3 Remove the Docker Engine and image-pull plans from `planners.py` and their prompts from
      `workflows/provision.py`; verify `provision apply` on this host offers no Docker step
- [ ] 4.4 Verify nothing references Docker in the package any more
      (`grep -rn "docker" odoo_dwg/` returns only unrelated matches, if any)

## 5. Docs

- [ ] 5.1 Update `docs/migration.md`: every step native, the ≤ 13 shape, and why the add-ons path is explicit
      (with the under-migration it caused)
- [ ] 5.2 Update `docs/provisioning.md`, `docs/support-matrix.md` and `README.md` to drop Docker as a
      prerequisite
- [ ] 5.3 Update `CHANGELOG.md` `[Unreleased]` and `docs/roadmap.md` (the native-12/13 question is answered;
      record that the container step under-migrated and is gone)

## 6. Acceptance

- [ ] 6.1 Run the four project checks green: `python -m pytest -q`, `python -m ruff check .`,
      `openspec validate --specs`, `python -m odoo_dwg --help`, plus the 3.10 floor run
- [ ] 6.2 Regenerate the 12 → 19 environment from scratch on this host (fresh checkpoints) and run the whole
      chain against the Odoo 12 demo dump; confirm it completes with the database at `base 19.0.1.3`
- [ ] 6.3 Confirm the defect that motivated this change is gone: in the final database `iap_account` has
      `company_ids` and no orphan `company_id`, and the 13.0 step's legacy columns match the native run
      (14 `openupgrade_legacy_*` columns at that point, not 13)
