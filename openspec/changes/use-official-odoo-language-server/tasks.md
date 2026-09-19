# Tasks

## 1. The language-server configuration

- [ ] 1.1 Add `WorkspaceConfig.odools_file` (`<root>/odools.toml`) and a helper returning a version's add-on
      directories without the core entry, derived from `addons_path`; verify a unit test asserts it equals
      `addons_path` minus the clone's `addons`
- [ ] 1.2 Add `templates.render_odools_toml(cfg)`: one `[[config]]` per version with exactly `name`,
      `odoo_path`, `addons_paths`, `python_path`, absolute paths, TOML-escaped strings; verify unit tests
      cover a two-version workspace, the absence of any `$` token, and that the output parses with `tomllib`
      where available
- [ ] 1.3 Write the file in `plan_workspace_tree`; verify a unit test asserts the plan writes `odools.toml`
      and no `jsconfig.json`

## 2. Official extension, one Python analyser

- [ ] 2.1 Recommend `Odoo.odoo` instead of `trinhanhngoc.vscode-odoo` in `render_vscode_extensions`; verify a
      unit test asserts both halves
- [ ] 2.2 Set `python.languageServer` to `None` in `render_vscode_settings`; verify a unit test asserts it

## 3. Docs

- [ ] 3.1 Document `odools.toml` and the editor setup in `docs/workspace-layout.md` (and the generated
      per-workspace README if it lists the tree)
- [ ] 3.2 Rewrite the roadmap item: delivered here, no companion dependency, and no remaining reference to the
      companion extension anywhere in the repository (`grep -rni companion` returns nothing outside git
      history)
- [ ] 3.3 Update `CHANGELOG.md` `[Unreleased]`

## 4. Acceptance

- [ ] 4.1 Run the project checks green, including the 3.10 floor run
- [ ] 4.2 Generate a two-version workspace on this host and confirm the rendered `odools.toml` points at the
      real clones and venvs; record the in-editor check (profile appears in the status bar) as a manual step
      rather than claiming it
