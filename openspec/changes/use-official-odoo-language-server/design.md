# Design

## Context

See `proposal.md` — Why. The facts this rests on, read from the official sources on 2026-09-19:

- `odoo/odoo-vscode` contributes a status-bar profile switcher (`odoo.clickStatusBar`, "Change
  Configuration"), an `Odoo.selectedProfile` setting, `Odoo.serverConfigPath`, and "Show Server Configuration
  (TOML/JSON)".
- The OdooLS wiki's configuration reference documents a *minimal config file* of `name`, `odoo_path`,
  `addons_paths`, `python_path` in an `odools.toml` at the workspace root; every other key is optional, and
  several are marked as applying only from a given release (`tsserver_command`, `disable_javascript`,
  `ts_check` from 1.5.0; semantic-token switches from 1.5.2).
- Auto-detection looks for `odoo/release.py` in the opened folders (and, from 1.5.0, their immediate
  children) and reports an error when more than one candidate qualifies. A generated workspace opens only its
  own root, and its Odoo sources sit in `<base>/.repos/odoo-<version>` — outside it, and possibly several.
- Setting `addons_paths` to any value turns auto-detection of add-ons off, which is what we want: the
  workspace knows its add-on directories exactly.

## Goals / Non-Goals

**Goals:**

- The official extension works on a freshly generated workspace with no manual setup.
- The emitted file survives OdooLS releases without being regenerated.

**Non-Goals:**

- Using OdooLS's own version machinery (`$version`, `${detectVersion}`, `${splitVersion}`). It is elegant, but
  it encodes the *directory layout* into the config, and the generator already knows the answer outright.
- Diagnostics tuning, stubs, languages, or anything else an operator may reasonably want to set by hand.
- Supporting the community extension alongside the official one.

## Decisions

### D1: Only the four documented minimal keys, as absolute paths

The minimal config is the part of the format least likely to move, and the only part whose meaning did not
change when 1.5.0 rewrote auto-detection. Absolute paths mean nothing in the file is interpreted by rules that
can change; every value is a fact the generator already writes into `config/odoo<major>.conf`.

*Alternative considered:* `${workspaceFolder}`-relative paths, so the workspace could be moved. Rejected: the
shared cache lives *outside* the workspace, so relative paths would need `..` segments whose resolution is
exactly the kind of detail that changes, and a moved workspace needs regenerating anyway (its `odoo.conf`
holds absolute paths too).

### D2: `addons_paths` is the workspace's `addons_path` minus core

`odoo.conf` lists custom, each OCA symlink, then the clone's `addons`. OdooLS loads core from `odoo_path`
itself, so the profile takes the same composition without its last entry — derived from the same model method
rather than restated, so the two can never disagree.

### D3: One profile per version, named after the workspace and version

`acme 18.0` reads clearly in the status bar switcher. A single-version workspace gets a single profile, which
the extension selects on its own.

### D4: Pylance off at workspace level

OdooLS and Pylance both analyse Python and would produce overlapping, sometimes contradictory diagnostics.
`python.languageServer: "None"` is a long-standing setting of the Python extension, and it is exactly what the
official extension offers to set through a prompt; the Python extension stays installed because debugging
(`launch.json`, `debugpy`) and interpreter selection still need it.

### D5: No `jsconfig.json`

From 1.5.0 OdooLS runs its own `tsserver` over the JavaScript and OWL templates declared in the manifests'
asset bundles — a better source of truth than any static path map. A `jsconfig.json` would start VSCode's
built-in TypeScript on the same files in parallel, and its path aliases would track Odoo's internal JS layout,
which shifts between versions. The trade-off, accepted: until 1.5 leaves beta, users on the stable 1.4
channel get no JavaScript intelligence from the language server.

## Risks / Trade-offs

- **The extension is still "in development"** by its own README → the file uses the smallest stable subset,
  and nothing in the tool depends on the extension being installed; ignoring it costs nothing.
- **A key is renamed upstream** → the verification is cheap (render, compare with the wiki's minimal example),
  and the four keys have been stable across the releases on record.
- **A workspace is moved** → its `odoo.conf` breaks the same way; regeneration fixes both, as today.

## Migration Plan

New workspaces get the file on generation. Existing ones get it through "manage" operations that already
rewrite the tree (adding a version regenerates the tree files).
