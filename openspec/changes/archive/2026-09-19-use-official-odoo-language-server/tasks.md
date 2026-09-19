# Tasks

## 1. The language-server configuration

- [x] 1.1 Add `WorkspaceConfig.odools_file` (`<root>/odools.toml`) and a helper returning a version's add-on
      directories without the core entry, derived from `addons_path`; verify a unit test asserts it equals
      `addons_path` minus the clone's `addons`
- [x] 1.2 Add `templates.render_odools_toml(cfg)`: one `[[config]]` per version with exactly `name`,
      `odoo_path`, `addons_paths`, `python_path`, absolute paths, TOML-escaped strings; verify unit tests
      cover a two-version workspace, the absence of any `$` token, and that the output parses with `tomllib`
      where available
- [x] 1.3 Write the file in `plan_workspace_tree`; verify a unit test asserts the plan writes `odools.toml`
      and no `jsconfig.json`

## 2. Official extension, one Python analyser

- [x] 2.1 Recommend `Odoo.odoo` instead of `trinhanhngoc.vscode-odoo` in `render_vscode_extensions`; verify a
      unit test asserts both halves
- [x] 2.2 Set `python.languageServer` to `None` in `render_vscode_settings`; verify a unit test asserts it

## 2b. Keeping up with the extension

- [x] 2b.1 Record the release the configuration was reviewed against (`ODOOLS_REVIEWED_VERSION = "1.4.0"`)
      next to the renderer, and the set of keys the renderer emits in one place both the renderer and the
      check read; verify a unit test asserts the rendered TOML uses exactly that set
- [x] 2b.2 Write `tools/verify_odools_config.py` (stdlib only, never imported by the package): latest stable
      release of `odoo/odoo-ls` → its `config_schema.json` → emitted keys accepted with compatible types
      (fail otherwise), unused keys listed, changelog since the reviewed version printed, prereleases
      reported but not judged; verify it exits zero today and non-zero when a key is perturbed
- [x] 2b.3 Write `docs/editor-integration.md`: the setup, why only four keys, and the update procedure —
      where to look, how to read the check, how a finding becomes a change, and what must never be emitted
      (beta-only keys, template variables); add the command to `CONTRIBUTING.md` and `CLAUDE.md`

## 3. Docs

- [x] 3.1 Document `odools.toml` and the editor setup in `docs/workspace-layout.md` (and the generated
      per-workspace README if it lists the tree)
- [x] 3.2 Rewrite the roadmap item: delivered here, with no dependency on a separate extension and no
      remaining reference to one anywhere in the repository (verified by grep, outside git history)
- [x] 3.3 Update `CHANGELOG.md` `[Unreleased]`

## 4. Acceptance

- [x] 4.1 Run the project checks green, including the 3.10 floor run
- [x] 4.2 Generate a two-version workspace on this host and confirm the rendered `odools.toml` points at the
      real clones and venvs, then run the official OdooLS binaries (stable and beta) against it with a probe
      module; record the in-editor status-bar check as the one remaining manual step
