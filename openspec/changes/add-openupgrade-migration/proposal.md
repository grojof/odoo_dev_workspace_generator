## Why

Migrating an old Odoo Community database up to a current version is the user's hardest, most error-prone task,
and the original motivation for a dedicated migration environment. OpenUpgrade (OCA) provides the scripts, but
each step must run under a Python matched to that Odoo version — and on Ubuntu 24.04 the early versions'
interpreters (3.5/3.6) are not natively obtainable. This change generates a reproducible OpenUpgrade migration
environment that chains 12 → 19 sequentially, solving the interpreter problem with a **data-backed** hybrid
strategy and a resumable, checkpointing driver.

## What Changes

- Add a **`migrate`** mode that, from a start/target version pair (e.g. 13 → 18), generates a migration
  environment under a dedicated root: per-target-version clones of `odoo/odoo` and `OCA/OpenUpgrade` (matching
  branch), a per-version virtualenv built by **`uv`** with the version-matched interpreter, per-step
  `odoo.conf`, and a **`run_migration.sh`** driver.
- **Interpreter strategy (validated on WSL Ubuntu 24.04):** `uv`'s installable floor is **3.8**, and its
  bundled-OpenSSL 3.8 works where pyenv fails. So Odoo **≥ 14 runs natively** (14/15 → 3.8, 16 → 3.10,
  17/18/19 → 3.12). Only the step that runs **Odoo 13** (Python 3.6) — i.e. a `12 → 13` migration — needs the
  **Docker fallback** (`odoo:13.0`, confirmed still pullable), likewise `odoo:12.0` if the source itself must
  run. The generator only emits the Docker recipe; the user's host provides the daemon.
- **Sequential, no skips** (per official OpenUpgrade): each step runs the target version's `odoo-bin` with
  `--upgrade-path=<ou>/openupgrade_scripts/scripts --update all --stop-after-init --load=base,web,openupgrade_framework`
  (the ≥ 14 module layout; the 12/13 branches use the older layout, templated per branch).
- **Checkpointing**: start from a *copy* of the source DB into a shared PostgreSQL, `pg_dump` after each
  successful step, and resume from the last good checkpoint on failure. Never touch production.
- **Requirements repair**: emit a per-version `overrides-<ver>.txt` (`psycopg2` → `psycopg2-binary`, floor
  lxml/Pillow/gevent/greenlet to a wheel-having release) for the old branches. wkhtmltopdf is not installed
  (migration uses `--stop-after-init`).

## Capabilities

### New Capabilities
- `migration-environment`: generation of the per-version clones, `uv` virtualenvs (matched interpreter +
  repaired requirements + openupgradelib), and per-step `odoo.conf` for an OpenUpgrade chain.
- `migration-run`: the checkpointing `run_migration.sh` driver — copy source DB → run each step in order →
  checkpoint on success → resume on failure — plus the Docker-fallback recipe for the Python-3.6 (Odoo 13) step.

### Modified Capabilities
<!-- None. Migration is additive; it reuses shared-cache and provisioning conventions but changes no spec. -->

## Impact

- **Code**: a version→interpreter→acquisition matrix in `models.py`; migration planners/templates in
  `planners.py`/`templates.py` (clones, `uv venv`/`uv pip`, overrides, per-step conf, `run_migration.sh`,
  Docker recipe); `workflows/migration.py` (menu, environment generation, run). Reuses the shared repo cache.
- **Host tools orchestrated**: `git`, `uv` (interpreters + venvs), `pg_dump`/`pg_restore`/`createdb`, and —
  only for the Odoo-13 step — `docker`. Checked before use; not Python dependencies.
- **Tests**: unit-test the interpreter matrix, the per-branch `odoo-bin` command shape (≥14 vs 12/13), the
  overrides, and the driver's step/checkpoint sequencing — pure, no real migration.
- **Docs**: `docs/migration.md` (the chain, interpreter table, Docker-fallback, checkpointing, official URLs).
- **Acceptance / scope**: a full 12 → 19 run needs a real legacy DB (out of unit scope); WSL acceptance covers
  environment generation + `uv` venv build + `odoo-bin --version` per native version. The Docker-13 step is
  validated by recipe + image existence (daemon is the user's env). Migrating custom modules' code is out of
  scope (that is `oca-port`/`odoo-module-migrator` territory, referenced in docs).
