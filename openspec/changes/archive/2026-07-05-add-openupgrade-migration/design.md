## Context

Migration is F3 — the hardest phase and the user's original driver. OpenUpgrade (OCA) supplies the scripts;
the risk was always the interpreters. That risk is now **closed with data measured on the WSL box** (Ubuntu
24.04 noble): `uv python install` floor is **3.8** (3.6/3.7 return "No download found"), a `uv` 3.8.20
interpreter imports `ssl`/`hashlib` fine (bundled **OpenSSL 3.0.14**, sidestepping the system-OpenSSL-3 wall
that breaks pyenv), and `odoo:12.0/13.0/14.0` images still return HTTP 200 on Docker Hub. This reshapes the
plan's original assumption: because each step runs the *target* version's `odoo-bin`, and Odoo 14 runs
natively on 3.8, **only the step that runs Odoo 13 (Python 3.6) needs Docker** — a source DB ≥ 13 migrates
entirely natively.

## Goals / Non-Goals

**Goals:**
- Generate a reproducible OpenUpgrade environment for a start → target chain: per-version clones, `uv`
  venvs with matched interpreters + repaired requirements + `openupgradelib`, per-step configs.
- A resumable, checkpointing `run_migration.sh` that operates on a *copy*, never production.
- Emit a Docker-fallback recipe only for the Python-3.6 (Odoo 13) step; text only.

**Non-Goals:**
- Running a full 12 → 19 migration in CI (needs a real legacy DB) — WSL acceptance covers env generation +
  `uv` venv + `odoo-bin --version` for native versions; the Docker step is validated by recipe + image
  existence.
- Migrating *custom module code* across versions — that is `oca-port` / `odoo-module-migrator`, referenced in
  docs, not reimplemented here.
- The official Odoo (Enterprise) upgrade platform — this is the community/OpenUpgrade route.

## Decisions

- **Interpreter matrix (data-backed)**: `models.migration_interpreter(major)` → `(python, method)`:
  14/15 → `("3.8","uv")`, 16 → `("3.10","uv")`, 17 → `("3.10","uv")`, 18/19 → `("3.12","uv")`, 13 →
  `(None,"docker")` (`odoo:13.0`), 12 → `(None,"docker")` (`odoo:12.0`). Rationale is the WSL measurements
  above. *Alternative:* pyenv/deadsnakes for 3.6 — rejected (pyenv fights OpenSSL 3; deadsnakes has no 3.6 for
  noble).
- **`uv` for venvs and installs** (`uv venv --python X`, `uv pip install`): a single self-contained binary,
  prebuilt interpreters (no compiler, no OpenSSL fight), and it sidesteps Ubuntu's PEP-668 `pip` restriction.
  *Alternative:* system `python3 -m venv` — rejected (only gives 3.12; can't match old versions).
- **Reuse the shared repo cache** (`.repos/odoo-<ver>`, `.repos/openupgrade-<ver>`) with the F1
  clone-if-absent planner, extended to clone `OCA/OpenUpgrade` on the matching branch.
- **Per-version `overrides-<ver>.txt`** repairs old pins (`psycopg2` → `psycopg2-binary`; floor
  lxml/Pillow/gevent/greenlet to wheel-having releases). Exact pins are hypotheses until a real `uv pip
  install` per version confirms them (Open Questions).
- **Checkpointing driver** over a shared **PostgreSQL 16**: restore source dump → working DB → checkpoint →
  for each step run `odoo-bin ... --update all --stop-after-init` → validate (exit 0, no traceback) →
  `pg_dump` checkpoint. Resumable from the last good checkpoint. *Alternative:* one-shot no-resume — rejected
  (a 7-step chain must not restart from zero on a late failure).
- **Per-branch command shape**: ≥ 14 uses `--upgrade-path=<ou>/openupgrade_scripts/scripts --load=base,web,
  openupgrade_framework`; 12/13 use the older integrated layout — templated per branch, never assumed.

## Risks / Trade-offs

- **Odoo-13 step needs Docker** → mitigation: recipe emitted against the shared PostgreSQL; steps communicate
  only through the DB + `pg_dump` checkpoints, so a containerized step interleaves seamlessly with native
  ones. If the source is ≥ 13, no Docker at all.
- **Old `requirements.txt` on new interpreters** → mitigation: the matched interpreter is the version's own
  (3.8 for 14/15), and `overrides` swap the few non-wheel pins; failures surface in the applied plan.
- **`pg_dump`/`pg_restore` version alignment** across native (PG16 client) and container steps → mitigation:
  all checkpoints produced/consumed by the shared PG16; the container connects to the same server.
- **Old OpenUpgrade command shape (12/13)** is only assumed until checked against those branches' READMEs
  (Open Questions).

## Migration Plan

Additive; reuses F1/F2 conventions. Land the matrix + planners/templates with unit tests (pure), then the
driver and `workflows/migration.py`. WSL acceptance: generate a small chain (e.g. 13 → 15), build the `uv`
venvs, run `odoo-bin --version` per native version, and lint the emitted `run_migration.sh` (`bash -n`). Full
data migration awaits a real legacy dump the user supplies.

## Open Questions

- Exact `overrides-<ver>.txt` pins per version (confirm by a real `uv pip install -r requirements.txt` for 14
  and 15 on the WSL box).
- The precise `odoo-bin` invocation for the OpenUpgrade 12.0/13.0 branches (verify against their READMEs before
  templating the Docker recipe).
- Whether to offer `--depth 1` clones for the migration env (history is irrelevant there) to cut disk/time —
  likely yes, unlike dev workspaces.
