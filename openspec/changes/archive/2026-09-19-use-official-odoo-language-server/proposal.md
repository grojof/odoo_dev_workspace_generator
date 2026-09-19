# Proposal

## Why

Generated workspaces recommend a community VSCode extension (`trinhanhngoc.vscode-odoo`) while Odoo now
publishes and actively maintains its own: the **OdooLS** language server (`odoo/odoo-ls`) and the
`Odoo.odoo` extension (`odoo/odoo-vscode`), released monthly in lockstep — stable 1.4.0, betas 1.5.x as of
2026-09-19 — with official plugins for PyCharm, Neovim and Zed as well.

The backlog carried a richer plan: a static emitter deferred until a separate, project-specific extension
settled profiles, version switching, a doctor and JavaScript support. The official project now covers every one of
those itself — `[[config]]` profiles switched from the status bar, per-version detection, a
"Show Server Configuration" view, and, from 1.5, JavaScript and OWL through its own `tsserver` reading the
manifests' asset bundles. Building on top of it would only add surface that breaks when it moves.

What the official extension cannot do alone is find *this* project's sources: its zero-config detection looks
for Odoo inside the opened folder, while a generated workspace opens only its own root and keeps Odoo in the
shared `.repos` cache, often in several versions at once. That gap is the one thing worth emitting.

## What Changes

- **Emit an `odools.toml` at the workspace root** with one `[[config]]` profile per Odoo version, using only
  the four keys of the official documentation's minimal configuration — `name`, `odoo_path`,
  `addons_paths`, `python_path` — filled with absolute paths the generator already knows (the same ones it
  writes into `config/odoo<major>.conf`). No template variables, no `extends`, no beta-only options: those are
  what changes between OdooLS releases, and a static file must not track them.
- **Recommend the official extension**: `Odoo.odoo` replaces `trinhanhngoc.vscode-odoo` in
  `.vscode/extensions.json`.
- **Turn the Python extension's language server off** for the workspace
  (`"python.languageServer": "None"`), so Pylance does not analyse Odoo code alongside OdooLS. It is what the
  official extension proposes through a prompt on first run; setting it up front removes the prompt.
- **No `jsconfig.json`**, deliberately: OdooLS 1.5 resolves JavaScript from the real asset bundles, a static
  `jsconfig` would run VSCode's own TypeScript over the same files in parallel, and its paths would depend on
  Odoo's internal JS layout, which changes between versions.
- **A documented, repeatable procedure for keeping up with the extension.** The language server publishes a
  `config_schema.json` with every release, and that schema is strict (`additionalProperties: false`: an
  unknown key is rejected). A stdlib-only `tools/verify_odools_config.py` downloads the schema of the latest
  stable release, checks that every key and type the generator emits is still accepted, lists the keys it
  does not use yet (new features to consider), and prints the changelog since the release last reviewed.
  `docs/editor-integration.md` explains where to look, how to read the result, and how a finding becomes a
  change — so adopting a new feature is a decision, not a surprise.
- The backlog item is rewritten accordingly and loses its dependency on that separate extension, which is no
  longer planned.

Out of scope: IDE integrations other than VSCode (the `odools.toml` is shared by every OdooLS client, so they
benefit anyway), and the `launch.json` debug shape, which remains its own validation item.

## Capabilities

### Modified Capabilities
- `workspace-generation`: a generated workspace carries the configuration the official Odoo language server
  needs to find its sources, and recommends the official extension.

## Impact

- **Code**: `templates.py` (`render_odools_toml`, the extensions and settings renderers), `planners.py`
  (write the new file with the tree).
- **Tooling**: `tools/verify_odools_config.py`, stdlib-only and outside the package, like
  `tools/verify_support_matrix.py`.
- **Docs**: a new `docs/editor-integration.md` (the setup and the update procedure),
  `docs/workspace-layout.md`, `CONTRIBUTING.md`, `docs/roadmap.md`, `CHANGELOG.md`.
- **Dependencies**: none. The file is plain TOML text; nothing is installed.
- **Verified on the reference host**, beyond rendering: a two-version workspace (14.0 and 18.0) was generated
  with the tool, and the official OdooLS binaries — 1.4.0 stable and 1.5.2 beta — were run against its
  `odools.toml` with a probe module. Both accepted the file under their strict schema, selected each profile by
  name, loaded the workspace's own interpreters (the `uv` 3.8 for 14.0, the host 3.12 for 18.0), resolved
  `res.partner` from core and reported only the probe's deliberate error. What remains manual is the editor
  UI itself — the status-bar switcher — which the CLI does not exercise.
