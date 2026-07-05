# odoo_dwg — AI Agent Guide (CLAUDE.md)

A zero-runtime-dependency (Python **standard library only**) generator that creates and maintains
**Odoo Community** *development* workspaces and *migration* environments on a **Linux host** (WSL Ubuntu
24.04, a server, or a container — the host is the user's choice, never provisioned implicitly). It is a
**user-run** CLI (it generates workspaces under the user's home and needs no root by itself; only
`provision apply` may escalate, and it says so). It never mutates the host directly: every host-mutating
action assembles a command **plan**, previews it, and applies it only after confirmation. This file is the
single authored source of truth for AI agents working *on* this project.

> **Status: F0 (foundation).** The package skeleton, i18n, UI/prompts, `system`, `models`, and the CLI/menu
> are in place; the three sections are navigable **stubs**. Real capability lands in F1 (workspace), F2
> (provision), F3 (migration). See `docs/roadmap.md` and the plan. Do not describe stubbed behavior as done.

## Project boundary & paths

- **This repository is the project root.** A single Python package, no nested repos.
- `odoo_dev_workspace_generator.py` — thin root entry point (also `python -m odoo_dwg` and the `odoo-dwg`
  console script).
- `odoo_dwg/` — the package, in strict layers (mirrors the sibling app `odoo_instance_manager`):
  - `models.py` — `WorkspaceConfig` / `InstanceConfig`, version facts, path/port derivation, JSON round-trip.
    Pure data + validation, **no I/O, no execution**.
  - `system.py` — execution primitives (`Command`, `run`, `run_streaming`), host probes, and the
    `preview_commands` / `apply_commands` contract.
  - `planners.py` *(arrives with F1/F2/F3)* — **pure** builders returning `list[Command]` (odoo.conf,
    VSCode files, venv/setup scripts, the migration driver). No I/O, no execution.
  - `prompts.py` — interactive input, `choose`, `confirm_with_phrase`.
  - `ui.py` — terminal tables and styling.
  - `i18n.py` — English-source translation with an optional Spanish catalog (`t`/`tf`).
  - `cli.py` — language selection, the interactive menu, and the argparse CLI.
  - `workflows/` — one module per user-facing surface: `workspace.py`, `provision.py`, `migration.py`.
  - `templates/` — text templates for generated artifacts (odoo.conf, VSCode, READMEs, bash scripts).
- `openspec/specs/` — the **behavior source of truth** (one spec per capability). Changes live in
  `openspec/changes/`; the `/opsx:*` flow drives them.
- `docs/` — user/operator docs, each with frontmatter. `docs/decisions/` holds ADRs. The README is the map.

## Non-negotiable principles

- **Zero runtime dependencies.** Python 3.10+, `from __future__ import annotations`, standard library only.
  The app *emits scripts and orchestrates system tools* (`git`, `python3 -m venv`, `pip`, `psql`/`createdb`,
  and — migration only — `uv`, optionally `docker`); those are **host prerequisites**, detected by
  `provision check`, not Python dependencies. Adding a runtime dependency is itself an ADR-worthy decision.
- **Preview → confirm → apply is inviolable.** Every host-mutating action goes through a previewed plan;
  destructive/data actions keep an exact-phrase confirmation (`confirm_with_phrase`). Never add a code path
  that mutates the host without a plan. **Keep planners pure** — building a command is not running it.
- **English is canonical** for code, docs, specs, and **all generated artifacts** (odoo.conf, scripts,
  per-workspace README). Spanish is offered only as an optional **UI** language via `odoo_dwg/i18n.py`: every
  operator-facing string goes through `t`/`tf` with the **English text as the source key** — never a
  hardcoded Spanish literal. Language is chosen at startup or via `ODWG_LANG=en|es`.
- **Anchor everything to OFFICIAL documentation.** Never assume an Odoo/OpenUpgrade fact (Python floor,
  wkhtmltopdf version, PostgreSQL minimum, migration command shape). Cite the official source in `docs/` and
  keep `models.ODOO_PYTHON_MINIMUM` / version facts traceable to it.
- **Host-agnostic.** `provision` prepares *a Linux host*; it must not assume WSL. The environment
  (Linux/WSL/Docker) is the user's, not this tool's.
- **No AI/MCP coupling.** The tool is assistant-agnostic and installs nothing AI-related. Its substitute for
  that is a **robust generated README** giving any assistant full context. Optional AI emitters (opt-in,
  text-only) are a future F4 concern, never a default.
- **Quote and validate every operator-supplied value** reaching a shell command or SQL string (`shlex.quote`
  and the identifier validators in `models.py`). Never interpolate raw input.

## How to work in this project

- **Non-trivial changes are spec-first.** Use the OpenSpec `/opsx:*` flow
  (`/opsx:explore → /opsx:propose <name> → /opsx:apply → /opsx:archive`); behavior is specified in
  `openspec/specs/`. Validate with `openspec validate --specs`.
- **Match the surrounding code**: small functions, early returns, type hints, LF newlines, final newline,
  UTF-8. Line length aims ≤100 (E501 is deferred for embedded shell/SQL strings).
- **Keep the root `README.md` current** as the friendly front door *and* routable map: what it does, the two
  sections + migration mode, a version/platform matrix, and links into `docs/`. Update it in lockstep with
  any behavior or docs change.
- **Keep the changelog and version in lockstep** (Keep a Changelog + SemVer). User-facing changes go under
  `## [Unreleased]` in `CHANGELOG.md`; bump `version` in `pyproject.toml` when cutting a release.
- **Some actions are irreversible or sensitive** (force-push, history rewrite, deleting a workspace/DB, secret
  access): pause and confirm first. Conventional Commits, imperative mood, one logical change per commit, **no
  AI-attribution trailers**.

## Testing & checks

- Tests are **standard library + pytest**, run without shelling out or touching the real filesystem (use
  `tmp_path`, assert on rendered template text and validated config objects). Never require a live Odoo/PG.
- The real end-to-end validation (a generated workspace actually cloning Odoo, building a venv, and launching
  `odoo-bin`) happens **on WSL Ubuntu 24.04** — it is intrinsically Linux and cannot be verified from Windows.

```bash
python -m pytest -q                 # unit tests
python -m ruff check .              # lint (E,F,I,UP,B,W; E501 deferred)
openspec validate --specs           # every capability spec is well-formed
python -m odoo_dwg --help           # CLI smoke test
```

## Safe controls

- Runtime guardrails come from the user-level **eunomai** Claude Code plugin (ask-by-default on force-push /
  `rm -rf` / secret access; deny on AI-attribution commit trailers). Fail-open — a floor-raiser, not a
  boundary. Project-level static path rules would live in `.claude/settings.json` if added.
