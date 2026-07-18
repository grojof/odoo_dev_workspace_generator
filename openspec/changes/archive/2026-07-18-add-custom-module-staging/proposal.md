# Proposal — add-custom-module-staging

## Why

A real migration's biggest manual cost is not the core database (OpenUpgrade covers it) but the **custom
modules**: their code must be adapted to every target version's breaking changes (e.g. 17.0 removes view
`attrs`/`states`, 18.0 renames `<tree>` to `<list>`) and may need per-version `migrations/` scripts when
they reference fields/models that change. Today the environment gives custom code a home
(`addons/odoo<major>/custom`, from add-migration-preflight) but the operator arrives there with raw,
unadapted source. The heavy mechanical work is already solved by OCA tooling — it just is not orchestrated.

## What Changes

- **A staging pipeline for custom modules**, as a new migration-menu action: for each custom module and
  each step of the chain, copy the previous step's staged code and run **`odoo-module-migrator`** (OCA)
  on it — the code-side complement of OpenUpgrade, with migration scripts for every bump through
  18.0→19.0 (manifest renames, `attrs` conversion, `tree`→`list`, removed-dependency detection…). Output
  lands in the environment's `addons/odoo<major>/custom` plus a per-module/per-step log of the tool's
  INFO / WARNING / ERROR findings.
- **Breaking-reference detection**: cross-reference each staged module's source against the OpenUpgrade
  **analysis files** of that step (`openupgrade_scripts/scripts/<module>/<ver>/upgrade_analysis.txt`,
  already cloned per version) to flag references to core fields/models that are removed or renamed in
  that step.
- **Migration scaffolds**: for each module/step with detected breaking references, emit a
  `migrations/<version>/pre-migration.py` stub (openupgradelib-based, one TODO per finding) — clearly
  marked as generated, never overwriting an existing file.
- **A staging report** the developer reviews: per module, per step — what was auto-applied, what was
  flagged, which scaffolds were written. The tool never claims a module is migrated; it delivers a robust
  starting point.
- `odoo-module-migrator` becomes a detected host prerequisite (installed into a dedicated uv-managed
  tool venv by an opt-in provision/migration plan), like git/uv/docker — never a runtime dependency of
  odoo_dwg.

Out of scope: semantic/AST-level transformations beyond what odoo-module-migrator provides; guaranteeing
functional equivalence (developer review is the contract); OCA modules (use the published migrated
branches — staging is for *custom* code only); running the staged modules' tests.

## Capabilities

### New Capabilities

- `migration-staging`: the custom-module staging pipeline — per-step orchestration of
  odoo-module-migrator, analysis-file cross-reference, migration scaffolds, and the review report.

### Modified Capabilities

- None — `migration-environment` requirements are unchanged; its docs gain a pointer to staging as the
  intended way to populate `addons/odoo<major>/custom` (docs-level, handled in tasks).

## Impact

- `odoo_dwg/planners.py` — staging plans (tool venv, per-step copy + migrate invocations, scaffold
  writes); `templates.py` — scaffold stub + report text; new pure analysis-file parser module
  (stdlib text parsing); `workflows/migration.py` — menu action + i18n; docs (`docs/migration.md`
  staging guide); tests for parser, planners, templates.
- Not verifiable from Windows: odoo-module-migrator behavior on real modules per bump, analysis-file
  coverage/format drift across branches (12–19), uv tool-venv install — WSL acceptance.
