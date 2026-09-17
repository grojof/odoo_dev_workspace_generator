# Tasks

## 1. Read what OpenUpgrade declares

- [ ] 1.1 Add a reader in `preflight.py` that parses a step's `openupgrade_scripts/apriori.py` with `ast`
      (never `exec`) and returns `renamed_modules` + `merged_modules` as one mapping; verify unit tests cover
      a file with both dicts, a file missing one, and an absent file returning an empty mapping
- [ ] 1.2 Cache the mapping per version within a run so a chain of seven steps parses each file once, and
      verify a unit test asserts the reader is called once per version

## 2. Classify what is left

- [ ] 2.1 Add the author classifier with the **exact** Odoo-spelling match from `design.md` D3; verify unit
      tests cover `Odoo S.A.`, `OpenERP SA`, an empty author, a vendor name, and
      `Odoo Community Association (OCA)` — the last one MUST be blocking, which is the substring trap
- [ ] 2.2 Rework `gather_coverage` to resolve through the mapping first and then split the remainder into
      blocking and warning classes per step; verify unit tests cover a renamed module, a merged one, a
      dropped Odoo-authored module, and an unaccounted vendor module
- [ ] 2.3 Carry the module author from the database into coverage (`gather_db_facts` returns name + author),
      and verify a unit test asserts modules with no author reach the classifier as blocking

## 3. Report the two classes

- [ ] 3.1 Update `preflight_rows` so blocking modules render as MISSING with the directory to fill and
      warnings render as WARN naming the reason; verify unit tests assert both states appear with the module
      and step named
- [ ] 3.2 Update the two callers in `workflows/migration.py` for the new return shape, and verify the
      preflight menu action still renders on this host against the `migration`-scoped database

## 4. Make the driver agree

- [ ] 4.1 Change the driver's embedded coverage check in `templates.py` to select `(name, author)`, resolve
      through `apriori.py` read at run time via the step's interpreter, and fail only on the blocking class;
      verify `templates.py` stays pure (no file reads at render time) and a unit test asserts the rendered
      script contains no absolute apriori content
- [ ] 4.2 Verify the regenerated driver passes `bash -n` and that its coverage section prints warnings for
      Odoo-dropped modules without exiting

## 5. Docs

- [ ] 5.1 Update `docs/migration.md`: what the coverage check blocks on, what it only warns about, and why
      (OpenUpgrade owns removing modules Odoo dropped)
- [ ] 5.2 Update `CHANGELOG.md` `[Unreleased]` and `docs/roadmap.md` (the 12 → 19 validation item records
      this finding and its fix)

## 6. Acceptance

- [ ] 6.1 Run the four project checks green: `python -m pytest -q`, `python -m ruff check .`,
      `openspec validate --specs`, `python -m odoo_dwg --help`
- [ ] 6.2 Regenerate the 12 → 19 environment on this host and rerun `run_migration.sh` against the Odoo 12
      demo dump; confirm it passes the coverage gate that currently aborts and reaches the first step
- [ ] 6.3 Let the chain run as far as it gets and record the outcome per step (checkpoints written, logs),
      whether it completes or fails somewhere — the point of the exercise is the real result, not a green
      tick
