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
- **VSCode official-extension emitter** — optional static emitter for the official `Odoo.odoo` extension:
  `odools.toml` profiles (verified schema: `[[config]]` + `name`/`extends`/`odoo_path`/`addons_paths`/
  `python_path`, vars `${workspaceFolder}`/`${detectVersion}`/`$autoDetectAddons`), an OWL `jsconfig.json`,
  stylelint wiring, and recommending `Odoo.odoo` in `extensions.json` (replacing the community pick).
  **Deferred until the sibling VSCode extension `odoo-ls-companion` stabilizes the format** — the dynamic
  logic (profiles, version switching, doctor) lives there, this emitter stays static. Sibling project:
  `C:\Users\GuillermousK\Desktop\CIFO\projects\Python\odoo-ls-companion`.
- **Provision password-auth mode** — instead of loopback `trust`, create the PostgreSQL role with a password
  and write `db_password` into the workspace `odoo.conf` (needs an `odoo.conf` password field). Safer for
  shared/remote PostgreSQL; the current trust is dev-only. (Deferred open question from F2 design.)

## Validation / refinement (host-dependent)

- ~~Migration overrides tuning~~ — **done** (2026-07-18): 14/15 install clean on 3.8; 16/17 needed the
  `--overrides` lift to `gevent==22.10.2`/`greenlet==2.0.2` (validated by real `uv pip install` on WSL).
- **12/13 OpenUpgrade command shape** — the recipe now runs the ≤ 13 *fork's* own `odoo-bin` from the
  mounted clone with `openupgradelib` installed on the fly (verified on WSL against `odoo:13.0`: container
  reaches OpenUpgrade code against the shared PostgreSQL). Remaining: semantic validation with a real
  legacy database (a synthetic dump cannot migrate).
- **Full 12 → 19 data migration** — run the checkpointing driver against a real legacy dump on WSL (needs a
  user-provided source database). Docker Engine is installed *in the Linux host itself* by
  `provision apply` (`docker.io`) — no Docker Desktop dependency; `odoo:12.0`/`odoo:13.0` tags verified
  still pullable (2026-07-18).
- **VSCode `launch.json` debug shape** — confirm the debugpy + `odoo-bin` launch config attaches against a
  real run on WSL (F1 open question).

## Ops

- **Push done**: repo is `grojof/odoo_dev_workspace_generator` (private). Make it public if desired.
- **LICENSE**: AGPL-3.0 in place; `pyproject` metadata consistent.
