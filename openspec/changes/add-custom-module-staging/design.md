# Design — add-custom-module-staging

## Context

add-migration-preflight gives custom modules a per-version home and flags them as needing adaptation;
this change fills that home with *prepared* code. Verified facts driving the design:

- `OCA/odoo-module-migrator` is a pip-installable python3 tool that migrates module **code** between
  versions and positions itself explicitly as the code-side complement of OpenUpgrade. It ships
  migration scripts for every bump through `migrate_180_190.py`, plus curated datasets
  (`removed_fields`, `renamed_fields`, `removed_models`, `renamed_models`, `deprecated_modules`,
  `text_replaces`, `text_warnings`) and logs INFO (auto-applied) / WARNING (check) / ERROR (must fix).
- OpenUpgrade branches ship per-module analysis files —
  `openupgrade_scripts/scripts/<module>/<ver>/upgrade_analysis.txt` (+ `_work.txt`) — listing core
  fields/models added/removed/renamed for that step. We already clone OpenUpgrade per version.

## Goals / Non-Goals

**Goals**: mechanical adaptation applied automatically per step; breaking references to changed core
fields/models surfaced with file/line; migration stubs pre-written; one report the developer works
through. **Non-Goals**: replacing developer review; transforming beyond the OCA tool's rules;
staging OCA modules (published migrated branches exist); executing or testing staged modules.

## Decisions

1. **Orchestrate `odoo-module-migrator`, never reimplement transformations.** The OCA maintains the
   per-version rules; odoo_dwg's value is wiring them into the chain. Alternative (own stdlib
   regex/AST transformer) rejected: unbounded maintenance surface, duplicates a maintained tool,
   violates "emit and orchestrate, don't reimplement".
2. **Tool venv via uv, as a host-prepared prerequisite.** `uv venv` + `uv pip install
   odoo-module-migrator` into `<base>/.tools/module-migrator` (shared across environments), planned
   and previewed like everything else. Keeps odoo_dwg itself dependency-free and pins the tool per
   host, not per Python process. Alternative (`uvx` ephemeral) rejected: version drifts between runs;
   a pinned venv is reproducible and offline-friendly after first install.
3. **Stage stepwise, never in place.** Input: an operator-supplied source directory of custom modules
   (their VCS checkout is never touched). Step N's staging input is step N−1's staged output
   (source → `addons/odoo13/custom` → … → target), mirroring the database chain — each bump applies
   only that bump's changes, exactly how the tool's scripts are organized. The copy lands via plan
   (`cp -a` then migrate) so preview shows precisely what is written where.
4. **Analysis cross-reference is a pure stdlib parser.** Parse `upgrade_analysis.txt` of the step's
   OpenUpgrade clone into (module, model, kind, old, new) records; grep staged custom source for
   occurrences of removed/renamed field and model names (word-boundary match, per file/line). Reported
   as candidates — a name match is a *lead*, not proof; the report says so. Alternative (Python AST
   resolution of field references) rejected as false precision: Odoo field references live in XML,
   domains, and strings as much as in Python.
5. **Scaffolds are additive and inert until reviewed.** `migrations/<target-version>/pre-migration.py`
   stubs contain a generated-file header, the openupgradelib import, and one commented TODO per
   finding (e.g. a `rename_field` call ready to uncomment). If the module already has that migration
   file, the stub is written alongside as `pre-migration.generated.py` for manual merge — never
   overwrite operator code (same rule as everywhere in odoo_dwg).
6. **Report format mirrors preflight**: per module × step rows (auto-applied / warnings / errors /
   findings / scaffolds written), rendered as the standard table plus a persisted
   `staging/report-<module>.md` in the environment for the developer to tick through.

## Risks / Trade-offs

- [odoo-module-migrator rules are community-maintained and uneven across bumps] → its WARN/ERROR log is
  carried verbatim into the report; staging never suppresses the tool's output.
- [Analysis files describe *core* modules only] → exactly the point: they detect custom code referencing
  changed core artifacts. Custom-to-custom changes remain developer work; the report states the boundary.
- [Name-match false positives] → findings are labeled candidates with file/line for one-look triage.
- [Tool needs network on first install] → part of the previewed plan; offline hosts skip staging.

## Migration Plan

Pure addition (new menu action + plans). No changes to existing generated artifacts beyond docs.
Rollback: `git revert`; staged outputs live only in the environment and are removable by the existing
clean action.

## Open Questions

- Pin `odoo-module-migrator` version or track latest? Leaning pin-with-override (reproducibility);
  decide at apply after testing on WSL against a real 12→19 stage of a sample module.
