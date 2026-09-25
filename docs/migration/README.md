---
type: how-to
title: "Migrating a database (OpenUpgrade 12 → 19)"
description: "Generate an OpenUpgrade migration environment and run the checkpointing driver."
tags: [migration, openupgrade, overview]
audience: [developer]
updated: 2026-09-25
---

# Migrating a database (OpenUpgrade 12 → 19)

The **migration** mode generates an [OpenUpgrade](https://github.com/OCA/OpenUpgrade) environment that upgrades
an Odoo Community database from an old version up to a current one. Migration is **sequential — no version
skips** (per OpenUpgrade): a 13 → 18 migration runs each of 14, 15, 16, 17, 18 in order.

```bash
python3 -m odoo_dwg migrate      # the migration menu
```

## The pages

In the order a migration is done. Generate the environment, take in the client copy, then generate again,
so that the core and the OCA repositories follow what the intake found.

1. [The migration environment](environment.md): what is generated, where code comes from, keeping the work.
2. [Taking in a client copy](intake.md): the client's dump, add-ons and configuration, audited before the chain.
3. [Working on a copy of production](production-copies.md): neutralising it, and keeping it from the outside.
4. [Running a migration](running.md): preflight, the driver, hooks, repairs, following a run, the report.
5. [Rehearsing a migration](rehearsing.md): on demo data before there is a client, and against a module built
   to break.
6. [Checks and findings](checks-findings.md): `migrate audit`, and the findings ledger with the client's decisions.

## Cleaning up

**Clean a migration environment** removes an environment directory (venvs, configs, checkpoints, logs,
requirements, driver) after a preview and the phrase `DELETE`. Use it to retest from scratch. The findings
ledger goes with it, and the confirmation says so: copy `findings/` first if you still need the client's
decisions. Removing the shared `.repos` clone cache is a separate opt-in, because it serves every
environment.

The working database is never touched. Drop it yourself for a fully clean run:
`dropdb -h 127.0.0.1 -U odoo migration_13_to_18` (named after the chain; `-h` and `-U` because the
development role is trusted over loopback TCP, not over the Unix socket).

## Scope & caveats

- **End-to-end chains are validated by hand** on the reference host: 12 → 19 on Odoo 12's demo data, and
  12 → 18 on a real client copy. The automated suite never runs Odoo.
- The 13.0 step runs the OpenUpgrade *fork's* own `odoo-bin`, because those branches predate
  `--upgrade-path` and `openupgrade_framework` ([layouts](environment.md#two-openupgrade-layouts)).
- **No container runtime:** every step, 13.0 included, runs in a `uv` virtualenv on the host.
- **Staging prepares custom module code; porting it is your review.** See also
  [`oca-port`](https://github.com/OCA/oca-port) and
  [`odoo-module-migrator`](https://github.com/OCA/odoo-module-migrator).

## Official references

- OpenUpgrade — running a migration: <https://oca.github.io/OpenUpgrade/040_run_migration.html>
- OpenUpgrade — introduction (sequential chaining): <https://oca.github.io/OpenUpgrade/010_introduction.html>
- openupgradelib: <https://github.com/OCA/openupgradelib>
- Odoo's own (Enterprise) upgrade platform, for contrast: <https://www.odoo.com/documentation/18.0/administration/upgrade.html>
