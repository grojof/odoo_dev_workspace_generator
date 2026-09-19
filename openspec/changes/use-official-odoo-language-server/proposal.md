# Proposal

## Why

Generated workspaces recommend a community VSCode extension (`trinhanhngoc.vscode-odoo`) while Odoo now
publishes and actively maintains its own: the **OdooLS** language server (`odoo/odoo-ls`) and the
`Odoo.odoo` extension (`odoo/odoo-vscode`), released monthly in lockstep — stable 1.4.0, betas 1.5.x as of
2026-09-19 — with official plugins for PyCharm, Neovim and Zed as well.

The backlog carried a richer plan: a static emitter deferred until a separate companion extension settled
profiles, version switching, a doctor and JavaScript support. The official project now covers every one of
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
- The backlog item is rewritten accordingly and loses its dependency on the companion extension, which is no
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
- **Docs**: `docs/workspace-layout.md` (the new file and the editor setup), `docs/roadmap.md`,
  `CHANGELOG.md`.
- **Dependencies**: none. The file is plain TOML text; nothing is installed.
- **Verifiable on the reference host**: generate a workspace with two versions and confirm the rendered
  `odools.toml` points at the real clones and venvs. Whether the extension then loads it is a manual check in
  VSCode — recorded as such, not claimed.
