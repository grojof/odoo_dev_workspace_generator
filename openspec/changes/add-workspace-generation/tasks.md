## 1. Model: profile & conventions (workspace-configuration)

- [x] 1.1 Extend `WorkspaceConfig` with OCA repository entries and a `save(path)` / stronger `load(path)` JSON round-trip; keep `from_dict` forward-compatible (ignore unknown keys).
- [x] 1.2 Add derived helpers needed by rendering: per-instance paths (`addons_custom`, `addons_oca`, `config_file`, `venv_dir`), shared cache paths (`odoo_clone_dir(version)`, `oca_clone_dir(repo, version)`), and the composed `addons_path(version)`.
- [x] 1.3 Unit-test naming, per-version non-colliding ports, `addons_path` ordering (custom→oca→odoo/addons), validation failures (bad name, unparseable version), and JSON round-trip. No filesystem/shell.

## 2. Templates & pure planners (workspace-generation rendering)

- [x] 2.1 Add `odoo_dwg/templates.py` string builders: `render_odoo_conf(cfg, version)`, `render_setup_venv_sh(cfg)`, `render_run_sh(cfg, version)`, VSCode `tasks.json`/`launch.json`/`settings.json`/`extensions.json`, `<name>.code-workspace`, and the per-workspace `README.md`. English text only.
- [x] 2.2 Add `odoo_dwg/planners.py` (pure): `write_text_file_command(path, content, mode)` helper; `plan_repo_cache(cfg, exists)` (clone odoo/OCA per version only when absent), `plan_workspace_tree(cfg)` (mkdirs, addons-oca per-version symlinks, config/vscode/scripts/README writes), `plan_build_venv(cfg, version, recreate)` (`python3 -m venv` + `pip install -r requirements.txt`). No I/O, no execution (existence injected).
- [x] 2.3 Unit-test rendered `odoo.conf` (composed `addons_path`, derived `http_port`, version-adaptive bus key), README (versions + ports + run commands), valid VSCode JSON, and that the tree plan only creates/writes (never builds a venv) while a present clone yields no clone command.

## 3. Workflow wiring (workspace-generation + workspace-management)

- [ ] 3.1 Implement `workflows/workspace.py` create flow: prompt/load a profile → validate → assemble `plan_repo_cache` + `plan_workspace_tree` + `plan_build_venv` → `preview_commands` → confirm → `apply_commands`. Refuse to clobber an existing workspace (create-only) and point to management.
- [ ] 3.2 Implement the manage flow: discover workspaces under `<base>` (exclude `.repos`/dotted), then regenerate/repair a venv (destructive → `confirm_with_phrase`), refresh shared repos, and add a version (reuse cache). Refuse a missing workspace.
- [ ] 3.3 Add an example profile under `examples/`; wire the menu entries and route errors back to the menu (RuntimeError handling already in `cli`). The plan → preview → confirm step is the non-destructive dry run — no separate flag.

## 4. Docs, checks & handoff

- [ ] 4.1 Add `docs/workspace-layout.md` and `docs/configuration-reference.md` (frontmatter), each citing the official Odoo "Source install" and CLI/`odoo.conf` reference URLs; update the root README map and `CHANGELOG.md`.
- [ ] 4.2 Run `ruff check .`, `python -m pytest -q`, `openspec validate --specs`, and `python -m odoo_dwg workspace` smoke; all green.
- [ ] 4.3 Record the WSL-only end-to-end validation steps (clone → venv → `odoo-bin` launch on Ubuntu 24.04) in `docs/` as the manual acceptance check, flagged as host-dependent.
