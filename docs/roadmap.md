---
type: explanation
title: "Roadmap (F0–F4)"
description: "Phased delivery plan for the Odoo dev/migration workspace generator."
audience: [contributor]
updated: 2026-07-05
---

# Roadmap

Delivery is phased so each phase is independently useful and verifiable. Non-trivial work in each phase is
proposed and tracked through OpenSpec (`/opsx:*`).

## F0 — Foundation *(in progress)*

Project scaffolding mirroring the sibling app `odoo_instance_manager`, plus conventions.

- Git repo, `.gitignore`, `pyproject.toml` (ruff + pytest, zero runtime deps).
- Package skeleton `odoo_dwg/`: `i18n`, `ui`, `prompts`, `system`, `models`, `cli`, `workflows/` (stubs).
- OpenSpec initialized (`openspec/`, `.claude/` commands + skills); `CLAUDE.md`; robust root `README.md`.
- Unit tests for `models` and `i18n`. **Done when** `python -m odoo_dwg --help`, `ruff`, and `pytest` are green.

## F1 — Workspace MVP *(the core value)*

JSON profile → full workspace layout: shared repo cache (`git clone --branch X --single-branch`), per-instance
venv, `addons-custom`/`addons-oca`, per-version `odoo.conf` (port offset per major), VSCode files, and a robust
per-workspace `README.md`. Development on 17/18/19. All generation is text; `apply` clones/builds via the plan.

## F2 — Provision *(optional, host-agnostic)*

`check` (report what a Linux host is missing) and `apply` (install it) as independent capabilities:
PostgreSQL + role, wkhtmltopdf (0.12.5 ≤14 / 0.12.6 ≥15), Node + rtlcss, per-version Python interpreters.
Never assumes WSL.

## F3 — Migration *(OpenUpgrade 12→19)*

Emit per-version clones + `uv` venvs with repaired requirements, per-step `odoo.conf`, and a checkpointing
`run_migration.sh` driver over a shared PostgreSQL 16 cluster. Optional Docker fallback for the versions whose
Python is impractical natively (12/13). Close the interpreter-strategy decision after validating on WSL.

## F4 — Optional AI emitters *(future)*

Opt-in, text-only emitters (CLAUDE.md/skills/agents for a user's assistant). Never installs runtimes; never a
default.

## Must-validate on WSL Ubuntu 24.04 (F3 risks)

Whether `docker pull odoo:12.0`/`13.0` still resolves; deadsnakes `python3.7` runtime on noble; the real `uv`
floor (3.7 vs 3.8); the exact `odoo-bin` shape for the 12.0/13.0 OpenUpgrade branches; the concrete
requirements overrides per interpreter; and `pg_dump`/`pg_restore` client alignment across native/container steps.
