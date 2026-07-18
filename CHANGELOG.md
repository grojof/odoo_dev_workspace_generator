# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- F0 foundation: package skeleton `odoo_dwg/` (i18n, ui, prompts, system, models, cli, workflow stubs),
  root entry point, interactive menu and argparse CLI (`workspace`/`provision`/`migrate`).
- English-canonical UI with an optional Spanish catalog (`ODWG_LANG=en|es`).
- Domain model: `WorkspaceConfig`/`InstanceConfig`, official Python-floor facts, deterministic per-version
  ports, JSON round-trip.
- Project conventions: `CLAUDE.md`, OpenSpec initialized (`openspec/`, `.claude/`), `docs/roadmap.md`,
  robust `README.md`, `pyproject.toml` (ruff + pytest, zero runtime dependencies).
- Unit tests for `models` and `i18n`.
- **F1 workspace section**: JSON-profile-driven generation of a per-client workspace — shared repo cache
  (`git clone --branch <ver> --single-branch`), per-version `odoo.conf`, per-instance venv, `addons-custom`/
  per-version `addons-oca` symlinks, VSCode files, `scripts/`, and a robust per-workspace README. Pure
  `templates.py` + `planners.py` (`plan_repo_cache`/`plan_workspace_tree`/`plan_build_venv`/
  `plan_generate_workspace`/`plan_refresh_repos`); create-only vs manage-only flows in `workflows/workspace.py`
  over plan → preview → apply. Example profile in `examples/`. Docs: `docs/workspace-layout.md`,
  `docs/configuration-reference.md`.
- **F2 provision section**: host-agnostic (Debian/Ubuntu apt) system provisioning. `provision check` renders a
  read-only host-readiness table; `provision apply` (root-gated, previewed, idempotent) installs the Odoo
  build dependencies, PostgreSQL + a dev role (with loopback trust for development), the checksum-verified
  patched wkhtmltopdf (0.12.6 for Odoo ≥ 15), and optional Node + rtlcss. New `provisioning.py` (facts + pure
  `provision_rows`), provision planners in `planners.py`, host probes in `system.py`, wired in
  `workflows/provision.py`. Docs: `docs/provisioning.md`. Validated end-to-end on WSL Ubuntu 24.04.
- **F3 migration mode**: generates an OpenUpgrade migration environment for a source → target chain
  (sequential, no skips). Data-backed interpreter strategy (measured on WSL): `uv` native interpreters for
  Odoo ≥ 14 (14/15→3.8, 16/17→3.10, 18/19→3.12) and a Docker fallback (`odoo:13.0`/`odoo:12.0`) for the
  Python-3.6/3.5 steps. `MigrationEnv` + `migration_chain`/`migration_interpreter` in `models.py`; migration
  planners (`plan_migration_clones`/`plan_migration_venvs`/`plan_migration_configs`/`plan_generate_migration`)
  and templates (per-step `odoo.conf`, checkpointing `run_migration.sh`, Docker recipe); wired in
  `workflows/migration.py`. Docs: `docs/migration.md`.

### Fixed
- Migration environment generation failed at the first requirements-overrides write
  (`cat > .../requirements/overrides-<ver>.txt`: "No such file or directory"): the `mkdir -p` for
  `requirements/` ran only in the configs planner, *after* the venvs planner that writes the overrides.
  `plan_migration_venvs` now creates the directory itself before its first write (found running a real
  12 → 18 generation on WSL).
- Migration venvs are now created with `uv venv --no-project`: without it, uv discovers any
  `pyproject.toml` at the caller's working directory (e.g. this repo's own, `requires-python >=3.10`)
  and emits a spurious incompatibility warning when building the 3.8 venvs for Odoo 14/15.
