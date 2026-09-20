# Rehearse before there is a client dump

## Why

Every path into a rehearsal starts from a dump the operator supplies. `run_migration.sh` takes one as its
argument and refuses to start without it. So until a client's database exists, the chain cannot be
exercised at all — and the first real migration doubles as the first test of the tool, on the data that can
least afford it.

Odoo ships demo data for exactly this, and OCA's own history supplies the interesting part. Across
12 → 19, `apriori.py` declares OCA modules with three different fates: **renamed**
(`account_consolidation` → `account_consolidation_oca` at 14.0), **merged into another module** — absorbed,
its records folded into the successor (`website_sale_product_style_badge` → `website_sale` at 14.0,
`partner_contact_lang` → `base` at 19.0) — and the large majority, which carry on under their own name.

A rehearsal that installs one of each answers the question the operator actually has before trusting the
tool with a client: *does a chain run end to end, and does a module that was absorbed end up where
OpenUpgrade says it does?*

## What changes

- **Fates are read with the distinction intact.** `read_apriori` merges `renamed_modules` and
  `merged_modules` into one mapping, which is right for coverage — both mean "the successor is X" — and
  loses the difference this needs. A second reader keeps it: renamed, or merged into.
- **`Module fates in this chain`**: for each module named, what the chain does to it and at which step —
  renamed to X, merged into Y, or nothing declared, which means it is expected to carry on. Derived from
  each step's own `apriori.py`, never assumed.
- **`Seed a demo source database`**: builds a database at the **source** version with Odoo's demo data and
  a chosen set of modules, then dumps it with `pg_dump -Fc` into the environment as the source dump the
  driver takes. The chain is then run exactly as it would be on a client's dump — same driver, same
  checkpoints, same tester, same report.
- **A suggested demo set**, offered rather than imposed: OCA modules of *this* chain that apriori gives
  different fates, **intersected with what is actually linked under the source version's `oca` directory**.
  A module that is not on disk at 12.0 cannot be installed at 12.0, and suggesting it would produce a
  rehearsal that fails for the wrong reason.
- **Module fates become probes too.** The tester derives its probes from the analysis files only; its spec
  allows `apriori.py` as a source and its change's task list claimed that reading. `renamed_module` and
  `merged_module` join the classes, so a module fate is checked after the step like any other subject.

## Impact

- Affected specs: `migration-environment`, `migration-preflight`
- Affected code: `odoo_dwg/preflight.py`, `odoo_dwg/analysis.py`, `odoo_dwg/tester.py`,
  `odoo_dwg/templates.py`, `odoo_dwg/planners.py`, `odoo_dwg/workflows/migration.py`, `odoo_dwg/cli.py`,
  `odoo_dwg/i18n.py`
- New: `tools/verify_demo_seed.py` — execute the generated seed against stub binaries
- Docs: `docs/migration.md`, `docs/commands.md`, `CHANGELOG.md`, `docs/roadmap.md`, `CONTRIBUTING.md`

## What this does not claim

The seed is verified here by executing its generated shell against stubs, and by ShellCheck. That a real
Odoo 12 installs a given OCA module, and that the chain then migrates it, is a fact only the reference host
can establish — this change is what makes that run possible, not a substitute for it.
