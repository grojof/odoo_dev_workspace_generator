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
