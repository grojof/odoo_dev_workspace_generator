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
