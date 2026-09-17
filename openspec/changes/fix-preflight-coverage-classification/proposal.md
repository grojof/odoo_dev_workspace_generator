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

Out of scope: acting on the warnings (OpenUpgrade owns uninstalling dropped modules), staging or migrating
the operator's modules (that is the existing staging surface), and anything about the support matrix.

## Capabilities

### Modified Capabilities
- `migration-preflight`: per-step addons coverage resolves OpenUpgrade's declared renames and merges, and
  distinguishes a core module dropped upstream (warning) from code the operator must supply (blocking).

## Impact

- **Code**: `preflight.py` (read and cache each step's `apriori.py`; classify by author; return the two
  classes separately), `templates.py` (the driver's embedded coverage loop mirrors the rule and only fails
  on the blocking class), and the installed-module query, which must return the author alongside the name.
- **Purity**: reading `apriori.py` is I/O and stays in `preflight.py`; the driver reads it at run time through
  the step's own interpreter, so `templates.py` and `planners.py` stay pure.
- **Docs**: `docs/migration.md` (what the coverage check blocks on and what it only warns about).
- **Tests**: the existing coverage tests inject module lists, which is how this survived — new cases cover a
  renamed module, a merged one, a dropped core module and an unaccounted operator module.
- **Verifiable on the reference host**: the 12 → 19 environment and the Odoo 12 demo dump are already built
  on this box, so the fix is checked by rerunning the driver that currently refuses.
