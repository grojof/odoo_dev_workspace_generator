---
type: explanation
title: "Roadmap (F0–F4) and backlog"
description: "Phased delivery plan and the parked backlog for the Odoo dev/migration workspace generator."
audience: [contributor]
updated: 2026-07-05
---

# Roadmap

Delivery is phased so each phase is independently useful and verifiable. Non-trivial work is proposed and
tracked through OpenSpec (`/opsx:*`); every phase below was accepted end-to-end on WSL Ubuntu 24.04.

## F0 — Foundation ✅

Package skeleton mirroring `odoo_instance_manager`, OpenSpec + `CLAUDE.md`, i18n (English/Spanish), CLI/menu.

## F1 — Workspace ✅ (accepted E2E)

JSON profile → shared repo cache, per-instance venv, `addons-custom`/per-version `addons-oca`, per-version
`odoo.conf`, VSCode files, per-workspace README; create-only vs manage-only over plan → preview → apply.
Accepted on WSL: a generated Odoo 18 workspace served HTTP 200 at `/web/login`.

## F2 — Provision ✅ (accepted E2E)

`check` (host-readiness table) + `apply` (build deps, PostgreSQL + dev role + loopback trust, checksum-verified
patched wkhtmltopdf, optional Node + rtlcss); apt-family only, root-gated. Accepted on WSL.

## F3 — Migration ✅ (accepted)

OpenUpgrade 12→19: per-version clones + `uv` venvs (matched interpreter) + per-step `odoo.conf` + checkpointing
`run_migration.sh`; Docker fallback for the Odoo-13 (Python 3.6) step. Interpreter decision closed with WSL
data (uv floor 3.8). Accepted on WSL: Odoo 15 runs on uv Python 3.8; driver passes `bash -n`.

---

# Backlog (next sessions)

Parked work, ordered roughly by value. Spec-driven items have (or should get) an OpenSpec change; validation
items are host-dependent.

## Features (OpenSpec)

- **F4 — Optional AI emitters** — opt-in, text-only emitters (CLAUDE.md / skills / agents for a user's
  assistant), never installing runtimes, never a default. A parked proposal exists:
  `openspec/changes/add-ai-emitters/` — fill it forward with `/opsx:` and apply.
- **Workspace shallow-clone option** — an opt-in `--depth 1` for dev workspace clones. F1 acceptance showed a
  full single-branch Odoo clone is ~394 MB; some users want history, some want speed. Add a profile flag.
  (Migration clones already use `--depth 1`.) Candidate for a small OpenSpec change.
- **CI workflow** — a GitHub Actions workflow running `ruff`, `pytest`, and `openspec validate --specs` on
  push/PR (mirror the sibling app's `.github/workflows/ci.yml`). Optionally a release workflow.
- **Provision password-auth mode** — instead of loopback `trust`, create the PostgreSQL role with a password
  and write `db_password` into the workspace `odoo.conf` (needs an `odoo.conf` password field). Safer for
  shared/remote PostgreSQL; the current trust is dev-only. (Deferred open question from F2 design.)

## Validation / refinement (host-dependent)

- **Migration overrides tuning** — confirm the exact `requirements/overrides-<ver>.txt` pins by a real
  `uv pip install -r requirements.txt` for Odoo 14 and 15 on the WSL box (psycopg2-binary already validated on
  15/3.8; check lxml/Pillow/gevent/greenlet floors).
- **12/13 OpenUpgrade command shape** — verify the exact `odoo-bin`/Docker invocation for the 12.0/13.0
  branches against their READMEs (they predate the `openupgrade_framework` module layout). The Docker recipe
  currently carries a `TODO` marker.
- **Full 12 → 19 data migration** — run the checkpointing driver against a real legacy dump on WSL (needs a
  user-provided source database). Docker Desktop WSL integration must be enabled for the 12→13 step.
- **VSCode `launch.json` debug shape** — confirm the debugpy + `odoo-bin` launch config attaches against a
  real run on WSL (F1 open question).

## Ops

- **Push done**: repo is `grojof/odoo_dev_workspace_generator` (private). Make it public if desired.
- **LICENSE**: AGPL-3.0 in place; `pyproject` metadata consistent.
