# Proposal

## Why

The per-step addons coverage check treats **every** module installed in the source database as code the
operator must supply, and the driver aborts the migration when any of them is missing. That is wrong for the
case the tool exists to serve: across a long chain, Odoo itself renames, merges and deletes core modules, and
OpenUpgrade already knows how to handle exactly those.

Found by the first real 12 → 19 run, against an Odoo 12 database built from Odoo's own demo data
(2026-09-17). The driver refused to start, reporting four core modules as missing on every step and telling
the operator to place them in `addons/odoo<major>/custom`:

- `web_editor` — OpenUpgrade declares `"web_editor": "html_editor"` in `openupgrade_scripts/apriori.py`
  (19.0, renamed).
- `web_kanban_gauge` — declared `"web_kanban_gauge": "web"` in the 17.0 `apriori.py` (merged).
- `web_settings_dashboard`, `web_diagram` — removed from Odoo Community outright after 12.0.

None of them is the operator's code and none of them can be "placed" anywhere. They are `auto_install`
dependencies of `base`, so **every** Odoo 12 database has them: the chain is unrunnable as shipped, and the
gate fires hardest exactly where the tool is most needed. The unit tests did not catch it because they inject
invented module lists; only a real database exposed it.

## What Changes

- **Resolve renames and merges before declaring anything missing.** Coverage consults the step's own
  OpenUpgrade checkout (`openupgrade_scripts/apriori.py`, which declares `renamed_modules` and
  `merged_modules` as plain dicts) and treats a module as covered when its declared successor resolves in
  that step's sources.
- **Classify what remains, instead of calling it all custom.** A module that resolves nowhere and that
  OpenUpgrade does not account for is judged by its author, as recorded in `ir_module_module`:
  - authored by Odoo — a core module dropped upstream: reported as a **warning**, because OpenUpgrade
    uninstalls it during the upgrade and there is nothing for the operator to do;
  - authored by anyone else (the operator's own modules, OCA, a vendor) — **blocking**, because that code
    genuinely has to be present for the step to run, and the report keeps naming the exact directory.
- **The driver stops aborting on the warning class.** It fails only on the blocking class, and prints the
  warnings with their reason. **BREAKING** only in the sense that a chain previously refused now runs.
- Both paths — the interactive preflight action and the checks embedded in `run_migration.sh` — apply the
  same rule, so the menu and the driver cannot disagree.
- **Pin `setuptools` for the steps that need `pkg_resources`.** Scope added while validating the fix above:
  with the gate passing, the chain then died at step 16 with
  `ModuleNotFoundError: No module named 'pkg_resources'`. Odoo ≤ 16 imports it at startup, `setuptools`
  removed it in 81, and nothing declares that dependency — `setuptools` arrives transitively and its version
  follows the step's interpreter, so the Python 3.8 steps resolved 75.x and worked while the 3.10 steps
  resolved 84.x and failed. The venvs for Odoo ≤ 16 now install `setuptools<81`, which is the pin
  `setuptools` itself recommends to `pkg_resources` users. It belongs in this change because the chain is
  unrunnable without both fixes, and neither was visible until a real database moved through it.

Out of scope: acting on the warnings (OpenUpgrade owns uninstalling dropped modules), staging or migrating
the operator's modules (that is the existing staging surface), and anything about the support matrix.

## Capabilities

### Modified Capabilities
- `migration-preflight`: per-step addons coverage resolves OpenUpgrade's declared renames and merges, and
  distinguishes a core module dropped upstream (warning) from code the operator must supply (blocking).
- `migration-environment`: a step's virtualenv pins a `setuptools` that still provides `pkg_resources` when
  that step's Odoo imports it, instead of leaving it to transitive resolution.

## Impact

- **Code**: `preflight.py` (read and cache each step's `apriori.py`; classify by author; return the two
  classes separately), `templates.py` (the driver's embedded coverage loop mirrors the rule and only fails
  on the blocking class), and the installed-module query, which must return the author alongside the name.
- **Purity**: reading `apriori.py` is I/O and stays in `preflight.py`; the driver reads it at run time through
  the step's own interpreter, so `templates.py` and `planners.py` stay pure.
- **Docs**: `docs/migration.md` (what the coverage check blocks on and what it only warns about).
- **Tests**: the existing coverage tests inject module lists, which is how this survived — new cases cover a
  renamed module, a merged one, a dropped core module and an unaccounted operator module.
- **Verified on the reference host**: with both fixes, a 12 → 19 chain ran end to end against an Odoo 12
  database built from Odoo's own demo data — eight checkpoints, `[done]`, and the working database at
  `base 19.0.1.3` with its data intact. The classification proved itself in the result: `web_editor` is gone
  and `html_editor` is installed (the rename OpenUpgrade declares), while the three modules Odoo dropped are
  simply no longer there.
