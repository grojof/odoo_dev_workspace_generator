# Rehearse with a module built to break

## Why

The chain can be rehearsed today, but only against the client's own add-ons. That answers *did this
migration work* one client at a time, and it answers it late: the first time a class of change is exercised
is the day a real module hits it.

The classes are knowable. OpenUpgrade states them, per step, in 2341 `upgrade_analysis.txt` files and in
`apriori.py`, and they are not exotic — across 14.0 → 19.0 they are dominated by a short list: a field
removed (473), a field that moved to another module (308), a model made obsolete (240), a field that stopped
being stored, stopped being related, became or stopped being a computed function, lost a selection key,
became company-dependent.

Some of those break loudly: the module will not load, and the step fails with a traceback. The dangerous
half is the quiet one — a field that moved module, or stopped being stored, leaves the module loading
perfectly and the column empty. Nothing in the run says so. `docs/migration.md` tells the operator to read
every step's log, and the log has nothing to report.

## What changes

The tool generates a custom add-on of its own, for the chain being rehearsed, whose only purpose is to
depend on each of those classes and to be caught when one of them takes something away.

- **The probes are derived, not invented.** Each one is built from a real record of that chain's own
  analysis files and `apriori.py` — this model is obsolete at 16.0, this field is `DEL` at 15.0, this one
  moves module at 17.0. A chain with no instance of a class gets no probe for it, and says so.
- **Each probe leaves a witness in its own table.** Installed on the source version, the module records
  what it could read then. The witness is ordinary data in the module's own table, so checking it afterwards
  is a `SELECT`, not an Odoo run.
- **A check reports, per step, which probes survived.** `intact`, `lost` (the witness is empty where it was
  not), `changed`, or `absent` (the module failed to load at all). A probe that is `lost` is the case that
  today passes silently.
- The module is generated into the environment like any staged module, and promoted like any other, so a
  correction made once is reused.

This is a rehearsal instrument, not something to install on a client's database. Its manifest says so, it
installs no menu and no access beyond its own tables, and the generator refuses to write it anywhere but a
migration environment.

## Impact

- Affected specs: `migration-preflight`
- Affected code: `odoo_dwg/analysis.py` (the classes it harvests), `odoo_dwg/tester.py` (new, pure),
  `odoo_dwg/templates.py`, `odoo_dwg/planners.py`, `odoo_dwg/workflows/migration.py`, `odoo_dwg/i18n.py`
- New: `tools/verify_migration_tester.py` — generate, byte-compile, parse the XML, and check the probe set
  against the analysis records it was derived from
- Docs: `docs/migration.md`, `docs/commands.md`, `CHANGELOG.md`, `docs/roadmap.md`, `CONTRIBUTING.md`
