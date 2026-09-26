# odoo_dwg — AI Agent Guide (AGENTS.md)

A zero-runtime-dependency (Python standard library only) CLI that generates and maintains **Odoo
Community** development workspaces and OpenUpgrade migration environments on a **Linux host**. This file is
a stable router: it says *where* things live and *which rules never change*. It deliberately holds no
project status — look that up in the files below.

## Where to look (and what to update)

| Need | Read / update |
|---|---|
| Current status, phases, backlog, next work | [`docs/project/roadmap.md`](docs/project/roadmap.md) |
| Work in flight | `openspec/changes/<name>/` (`proposal.md`, `design.md`, `tasks.md`) |
| Behavior source of truth (per capability) | `openspec/specs/<capability>/spec.md` |
| Why a decision was made | `openspec/changes/archive/*/design.md` (no separate ADR series) |
| OpenSpec project context & artifact rules | [`openspec/config.yaml`](openspec/config.yaml) |
| What the tool does, user-facing map | [`README.md`](README.md) |
| Commands, menus, confirmation phrases | [`docs/reference/commands.md`](docs/reference/commands.md) |
| What is supported (hosts, Python, PostgreSQL) | [`docs/reference/support-matrix.md`](docs/reference/support-matrix.md) — declared in `models.py`, re-verified by `tools/verify_support_matrix.py` |
| Editor integration (official Odoo extension) and its update procedure | [`docs/workspace/editor.md`](docs/workspace/editor.md) — re-verified by `tools/verify_odools_config.py` |
| Workspace profile / layout, per-version venv rules | [`docs/workspace/configuration.md`](docs/workspace/configuration.md), [`docs/workspace/layout.md`](docs/workspace/layout.md) — re-verified by `tools/verify_workspace_versions.py` |
| Outbound firewall + mail capture, and their update procedure | [`docs/host/egress-control.md`](docs/host/egress-control.md) — pins in `odoo_dwg/egress.py`, re-verified by `tools/verify_egress_pins.py` |
| Provisioning / migration guides | [`docs/host/provisioning.md`](docs/host/provisioning.md), [`docs/migration/README.md`](docs/migration/README.md) — the generated driver is re-verified by `tools/verify_migration_driver.py` |
| Contribution rules, checks, commits | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| User-facing change log & version | [`CHANGELOG.md`](CHANGELOG.md) (`[Unreleased]`), `__version__` in [`odoo_dwg/__init__.py`](odoo_dwg/__init__.py) (read by `pyproject.toml`) |

When a change lands, keep these in lockstep: the spec (via `/opsx:archive`), `README.md` + the relevant
`docs/` page, `CHANGELOG.md`, and `docs/project/roadmap.md` (move items from backlog to done).

## Code layout (layer contract)

The package `odoo_dwg/` is layered; respect the direction of dependencies:

- `models.py` — config dataclasses, version facts, path/port derivation, identifier validators. Pure data.
- `planners.py` + `templates.py` — **pure** builders returning `list[Command]` / rendered text. No I/O.
- `system.py` — the only place that executes (`run`, `run_streaming`, host probes,
  `preview_commands` / `apply_commands`).
- `ui.py`, `prompts.py`, `i18n.py` — terminal output, input/confirmation, translation.
- `workflows/` — one module per surface (`workspace`, `provision`, `migration`) wiring the above.
- `cli.py` — language selection, interactive menu, argparse. Entry points: `python -m odoo_dwg`,
  `odoo-dwg`, `odoo_dev_workspace_generator.py`.

Other modules (e.g. `provisioning.py`, `preflight.py`, `analysis.py`) follow the same rule: pure logic
unless they are `system.py`.

## Non-negotiable principles

- **Zero runtime dependencies.** Python 3.12+, `from __future__ import annotations`, stdlib only. System
  tools (`git`, `uv`, `psql`…) are host prerequisites detected by `provision check`, never Python
  deps. Adding a runtime dependency requires a documented design decision.
- **Plan → preview → confirm → apply is inviolable.** No code path mutates the host without a previewed
  plan; destructive/data actions require `confirm_with_phrase`. Planners stay pure.
- **English is canonical** for code, docs, specs, and all generated artifacts. Spanish is only an optional
  UI language: every operator-facing string goes through `t`/`tf` with the English text as key, and
  `odoo_dwg/i18n.py` is authored in that direction (English → Spanish), never inverted.
  **Technical terms stay in English** in the Spanish UI — `workspace`, `host`, `dump`, `venv`, `commit`,
  `log`, `loopback`, `staging`, `worktree`, `addons`, `custom`, `pg_hba` — because that is what a
  Spanish-speaking Odoo developer says; translating them reads worse than leaving them. Translate the
  sentence around them.
- **Anchor Odoo/OpenUpgrade facts to official sources**, cited bound by bound in
  `docs/reference/support-matrix.md` and declared once in `models.py`; never assume them, and never restate a
  bound elsewhere. Each bound carries its evidence tier (`official`/`derived`/`untested`).
- **Host-agnostic.** Target "a Linux host"; never assume WSL. The environment is the user's choice.
- **No AI/MCP coupling.** Install nothing AI-related and emit nothing assistant-specific; the generated
  per-workspace README is the context source for any assistant.
- **Quote and validate** every operator-supplied value reaching a shell or SQL string (`shlex.quote`,
  validators in `models.py`).

## How to work

- **Non-trivial changes are spec-first**: `/opsx:explore → /opsx:propose <name> → /opsx:apply →
  /opsx:archive`. Trivial fixes may go direct.
- Match the surrounding code: small functions, early returns, type hints, LF, UTF-8, final newline, lines
  ≤100 (E501 deferred for embedded shell/SQL).
- Conventional Commits, imperative mood, one logical change per commit, **no AI-attribution trailers**.
- Pause and confirm before irreversible or sensitive actions (force-push, history rewrite, deleting a
  workspace/DB, secret access).
- **Edit files one edit at a time, with a tool that fails per edit.** A script doing several substitutions
  must report each one (applied / not found) instead of asserting, because an abort halfway leaves the rest
  silently unapplied. Before committing, grep for the new text of every change the commit message claims:
  twice in this repo a commit described edits that were never in the diff.
- **Text that is executed is verified by executing it**, not by reading it: rendered shell through
  `tools/verify_*.py`, a regex against the real inputs it must and must not match. Two bugs here (a `sed`
  backreference left dangling by a changed capture group, a `grep` pattern eaten by shell quoting) were
  invisible in review and immediate on the first run.

## Checks

Tests use stdlib + pytest only: no shelling out, no real filesystem (use `tmp_path`), no live Odoo/PG.

```bash
python -m pytest -q                 # unit tests
python -m ruff check .              # lint (E,F,I,UP,B,W; E501 deferred)
openspec validate --specs           # specs well-formed
python -m odoo_dwg --help           # CLI smoke test
```

These are not in the suite. **What each one covers and needs is stated once**, in
[`CONTRIBUTING.md`](CONTRIBUTING.md) — restating it here is how it drifted four audit rounds running:

```bash
python tools/verify_support_matrix.py      # the support matrix, re-derived from its official sources
python tools/verify_odools_config.py       # the editor config vs the latest official OdooLS release
python tools/verify_workspace_versions.py  # build + start Odoo 12-19 in a throwaway workspace
python tools/verify_egress_pins.py         # OpenSnitch/Mailpit pins vs their signed/published sources
python tools/verify_migration_driver.py    # the generated migration driver, against stub binaries
python tools/verify_generated_shell.py     # ShellCheck over every generated script
python tools/verify_pg_hba_trust.py        # the pg_hba rewriter, against a throwaway PostgreSQL
python tools/verify_promoted_modules.py    # the promote / consume cycle, with a stub module migrator
python tools/verify_mail_capture.py        # mail capture, check and restore, against a throwaway PostgreSQL
python tools/verify_migration_tester.py    # the rehearsal tester: it is a module, and its query runs
python tools/verify_demo_seed.py           # the generated demo seed, against stub binaries
python tools/verify_neutralisation.py      # neutralise, check, re-apply and restore, against a throwaway PostgreSQL
python tools/verify_neutralise_sources.py  # the neutralisation catalogue vs the sources it cites
python tools/verify_intake.py              # intake on real tools: restore, reader role, core, audits, bank lines, journal codes
python tools/verify_migration_audit.py     # migrate audit on 12.0- and 18.0-shaped databases, against a throwaway PostgreSQL
python tools/verify_grouped_invoice_lines.py  # the repair of grouped invoice items, against a throwaway PostgreSQL
python tools/verify_source_taxes.py        # keep a source's journal-item taxes, take back OpenUpgrade 13.0's additions
```

End-to-end validation (cloning Odoo, building venvs, running `odoo-bin`, migrations) happens on a real
Linux host — WSL Ubuntu 24.04 is the reference box; it cannot be verified from Windows.

## Safe controls

Runtime guardrails come from the user-level **eunomai** Claude Code plugin (fail-open floor-raiser, not a
boundary). Project-level static rules would go in `.claude/settings.json` if added.
