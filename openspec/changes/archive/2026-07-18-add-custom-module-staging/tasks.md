# Tasks — add-custom-module-staging

## 1. Analysis parser (pure)

- [x] 1.1 New `odoo_dwg/analysis.py`: stdlib parser of `upgrade_analysis.txt` into
      (module, model, kind, old, new) records; word-boundary scanner over .py/.xml text returning
      (file, line, finding) candidates. Unit tests on fixture text (no filesystem beyond tmp_path).

## 2. Model & planners

- [x] 2.1 `models.py`: tool-venv path helper (`<base>/.tools/module-migrator`), staging dirs/report
      paths on `MigrationEnv`; tests.
- [x] 2.2 `planners.py`: `plan_staging_tool()` (uv venv + `uv pip install odoo-module-migrator`,
      pin decision from design open question); `plan_stage_module(env, module, src)` — per-step
      `cp -a` + tool invocation with that bump's `--init-version-name/--target-version-name`
      (verify exact CLI flags during apply); scaffold write commands (additive rule). Pure tests
      asserting command text, ordering, and the never-overwrite sibling naming.
- [x] 2.3 `templates.py`: `render_migration_scaffold(findings)` (header, openupgradelib import,
      commented TODO per finding) and `render_staging_report(...)`; template tests.

## 3. Workflow & preflight wiring

- [x] 3.1 `workflows/migration.py`: "Stage custom modules" menu action — pick environment, source dir,
      modules (all or subset); preflight gate (tool venv present, chain clones present); preview/apply;
      print report path. i18n strings ES.
- [x] 3.2 Preflight (`preflight.py` from add-migration-preflight): staging-tool row when staging is
      requested; coverage check recognizes staged modules.

## 4. Docs & bookkeeping

- [x] 4.1 `docs/migration.md`: staging guide — what the tool auto-applies per bump (with the 17.0
      `attrs` / 18.0 `tree→list` examples), what candidates mean, how to finish a scaffold; boundary
      statement (developer review completes the migration). Reference OCA odoo-module-migrator and the
      OpenUpgrade analysis-files docs as the anchors.
- [x] 4.2 README + CHANGELOG under [Unreleased]; ruff + pytest green.

## 5. WSL acceptance

- [x] 5.1 Install the tool venv via the plan; verify `odoo-module-migrator --help` and pin the working
      version (close the design open question).
      *(Done 2026-07-18: plan applied verbatim, CLI works, pinned ==0.5.0 as STAGING_TOOL_SPEC.)*
- [x] 5.2 Stage a real sample custom module 12 → 19 (or 16 → 18 minimum): confirm attrs→expressions and
      tree→list are applied, WARN/ERROR carried into the report, a seeded removed-field reference is
      detected from the 17.0/18.0 analysis files, and the scaffold lands additively.
      *(Done: 16 → 18 stage of a sample module — source untouched, tree→list applied at 18.0, manifest
      version bumped per step, logs captured per step; the seeded ir.cron.doall reference was detected
      at models/cron_ext.py:9 from 292 analysis records and the scaffold written with its TODO.
      Findings: the tool needs a git worktree (planner now prepares one per stage dir) and 0.5.0 does
      NOT auto-convert 17.0 attrs — docs adjusted to observed behavior. Additive sibling naming is
      unit-covered.)*
