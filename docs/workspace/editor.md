---
type: how-to
title: "Editor integration (official Odoo extension)"
description: "What a generated workspace gives the official Odoo language server, why so little, and the procedure to review its updates and adopt new features."
audience: [developer, contributor]
updated: 2026-09-20
---

# Editor integration

Generated workspaces are set up for the **official** Odoo tooling: the OdooLS language server
([`odoo/odoo-ls`](https://github.com/odoo/odoo-ls)) and its VSCode extension `Odoo.odoo`
([`odoo/odoo-vscode`](https://github.com/odoo/odoo-vscode)). OdooLS also has official plugins for PyCharm,
Neovim and Zed; they read the same `odools.toml`, so everything below applies to them too.

The integration is deliberately small. OdooLS is under active development — its own README says it is
*"not released in a stable and valid version"* — and it changes monthly. Everything the tool emits is chosen
to survive those releases without regeneration.

## What a workspace gets

| File | Content | Why |
|---|---|---|
| `odools.toml` (workspace root) | One `[[config]]` profile per Odoo version ≥ 14, with `name`, `odoo_path`, `addons_paths`, `python_path` as absolute paths | OdooLS's zero-config detection looks for Odoo *inside* the opened folder; a workspace keeps it in the shared `.repos` cache, often in several versions |
| `.vscode/extensions.json` | Recommends `Odoo.odoo` (plus `ms-python.python` and `ms-python.debugpy`) | The official extension, not a third-party one |
| `.vscode/settings.json` | `"python.languageServer": "None"` | OdooLS analyses Python; Pylance on the same files would duplicate and contradict it. The Python extension stays for debugging and interpreter selection |
| `.vscode/launch.json` | Four debugpy configurations per version, plus prompts for their inputs (see below) | The everyday entry points of Odoo development, each under the debugger |

Pick a profile from the status bar (**Change Configuration**). A single-version workspace has one profile,
selected on its own. **Show Server Configuration (TOML/JSON)** in the command palette displays what the server
actually loaded.

### Debug configurations (F5)

Each version gets four configurations. All four run that version's `odoo-bin` from its venv, in the integrated
terminal, with `justMyCode` off so breakpoints stop in Odoo's code as well as yours:

| Configuration | Arguments | Asks for |
|---|---|---|
| `Odoo <version> (<instance>)` | `-c config/odoo<major>.conf` | — |
| `Odoo <version> shell (<instance>)` | `shell -c … -d <database>`: a Python REPL with `env` bound to the database | database (default: the workspace name) |
| `Odoo <version> upgrade modules (<instance>)` | `-c … -d <database> -u <modules>`, then keeps serving | database, modules (comma-separated) |
| `Odoo <version> test module (<instance>)` | `-c … -d <database> -u <module> --test-enable --test-tags /<module> --stop-after-init` | database, module |

The prompts are `launch.json` `inputs` (`odooDatabase`, `odooModules`, `odooTestModule`), so VS Code asks for
them when the configuration starts. `tools/verify_workspace_versions.py` runs these same configurations from the
generated file, with the prompts answered, on every version:
- **shell:** an ORM query is piped in and must come back.
- **test module:** `barcodes`' tests must run and pass.
- **upgrade modules:** the server must serve `/web/login`.

**Odoo 12 runs tests only on a database with demo data.** Its loader skips them otherwise
(`odoo/modules/loading.py`: "launch tests only in demo mode"), so the test configuration exits cleanly
having run nothing. From 13 on, tests run either way.

Deliberately not included:
- **Auto-reload:** Odoo's `reload` re-executes the process, which detaches the debugger. The generated
  `odoo.conf` therefore sets `dev_mode = qweb,xml` and never `reload`, so installing `watchdog` (which Odoo's
  requirements do not include) cannot silently start detaching it.
- **Attach, `scaffold` and the other subcommands:** they are rarely debugged, and each would add one more
  entry per version to the picker.

### What is deliberately *not* emitted

- **Any key beyond the four minimal ones.** The schema OdooLS validates against is strict
  (`additionalProperties: false`): one unknown key makes the whole file invalid. Anything else — diagnostics,
  stubs, languages — is yours to add below the generated profiles.
- **Template variables** (`${workspaceFolder}`, `$version`, `${detectVersion}`, `$autoDetectAddons` …). They
  encode the directory layout into rules that have already changed once (1.5.0 rewrote auto-detection); the
  generator knows the answers outright.
- **Keys documented as applying from a given release** — for instance the 1.5 JavaScript options
  (`disable_javascript`, `ts_check`, `tsserver_command`). They appear in the wiki before they appear in a
  *stable* schema, and emitting one would break every install still on the stable channel.
- **A `jsconfig.json`.** From 1.5 OdooLS runs its own `tsserver` over the JavaScript and OWL templates declared
  in the manifests' asset bundles. A static `jsconfig.json` would start VSCode's built-in TypeScript on the same
  files in parallel, and its path aliases would follow Odoo's internal JS layout, which shifts between versions.
  Until 1.5 leaves beta, the stable 1.4 channel has no JavaScript support from OdooLS.
- **Profiles for Odoo 12 and 13.** OdooLS refuses versions below 14. The file names the skipped versions in a
  comment; a workspace with no supported version gets no `odools.toml`.
- **The core `addons` directory in `addons_paths`.** In an editor OdooLS adds `<odoo_path>/addons` by itself,
  and it does not deduplicate: listing it would load core twice. *Consequence for the one-shot CLI*
  (`odoo_ls_server --parse`), which does not add it: pass `-a <odoo_path>/addons` yourself, exactly as the
  official CLI documentation instructs.

## Keeping up with the extension

A review answers two questions: *does what we emit still work*, and *is there something new worth emitting*.
The first must be answered before a generated file can break; the second is a decision, never automatic.

### 1. Run the check

```bash
python tools/verify_odools_config.py
```

Run it when the extension announces an update, before changing what `templates.render_odools_toml` emits, and
every few months otherwise. It needs the network, is not part of the test suite, and never edits anything.

It reads the **latest stable** release of `odoo/odoo-ls`, downloads that release's `config_schema.json` asset,
and reports:

| Section | Meaning | Action |
|---|---|---|
| `Emitted keys` — `ok` / `FAIL` | Each key the generator writes, checked against the stable schema: present, and still accepting the type we write | Any `FAIL` exits non-zero and **must** be fixed (step 3) |
| `Keys the generator does not emit` | Everything else the stable schema accepts | Candidates only — read them, adopt nothing by default |
| `Changelog since <reviewed>` | Every release note newer than `ODOOLS_REVIEWED_VERSION`, tagged `<stable>` or `<prerelease>` | Read them; this is where new behaviour and new keys are announced |

Prereleases are reported but never judged: their keys are not safe to emit until a stable schema has them.

### 2. Read what changed

For each entry in the changelog, ask:

- **Does it change the meaning of a key we emit** (`name`, `odoo_path`, `addons_paths`, `python_path`)? Then
  the generated file may be wrong even though the check passes — treat it like a `FAIL`.
- **Does it change how core or add-on paths are resolved?** Re-check the `addons_paths` decision above against
  the source (`server/src/core/odoo.rs`, around the handling of `odoo_path` and `load_odoo_addons`).
- **Does it add a stable key the workspace can fill with a fact the generator already knows?** That is the only
  kind of new key worth emitting. Keys that express a *preference* (diagnostics, stubs, languages) stay with
  the operator.
- **Does it change the extension's settings** (for instance something that affects `python.languageServer`)?
  Look at `contributes.configuration` in `odoo/odoo-vscode`'s `package.json` at the release tag.

### 3. Apply the result

| Outcome | What to do |
|---|---|
| A `FAIL`, or a changed meaning | Open a change (`/opsx:propose`), fix the renderer, its tests and this page, and bump `ODOOLS_REVIEWED_VERSION` in the same change |
| A new stable key worth emitting | Same, spec-first: add it to `ODOOLS_KEYS` and to `EMITTED_TYPES` in the check, render it, test it, document it here, bump `ODOOLS_REVIEWED_VERSION` |
| Nothing to adopt | Bump `ODOOLS_REVIEWED_VERSION` (in `odoo_dwg/templates.py`) to the stable release you reviewed, in a small direct commit, so the next review starts from there |
| A feature exists only in a prerelease | Nothing yet. Note it in `docs/project/roadmap.md` if it matters, and revisit when a stable schema carries it |

Existing workspaces pick up a changed `odools.toml` with **Manage an existing workspace → Refresh generated
files**, which rewrites only the files that changed and keeps a dated backup of each.

### Where the facts live, and the traps

Read these at the **release tag**, not at a branch:

| What | Where |
|---|---|
| Releases and their channel | `https://github.com/odoo/odoo-ls/releases` (stable vs *Pre-release*) |
| The schema OdooLS validates `odools.toml` against | the `config_schema.json` asset of each release |
| Release notes | `changelog.md` **and** `changelog_archive.md` at the tag |
| The configuration reference | the wiki page *3. Configuration files* |
| The extension's settings and commands | `package.json` → `contributes` in `odoo/odoo-vscode` at the tag |

Traps, all hit while building this:

1. **`changelog.md` keeps only the latest entry**; every earlier one moves to `changelog_archive.md`. Reading
   one file shows a single release.
2. **Prerelease notes live on the `beta` branch and the prerelease tags only.** `master` and `release` both
   look up to date when they are not.
3. **The wiki documents keys before they are stable.** The 1.5 JavaScript options are in the wiki but not in
   the 1.4.0 stable schema. The schema of a *stable* release is the authority for what may be emitted.
4. **The schema is strict.** An unknown key does not get ignored; it invalidates the file.
5. **The CLI and the editor load core differently** (see *What is deliberately not emitted*).
