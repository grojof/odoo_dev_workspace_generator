---
type: how-to
title: "Migrating a database (OpenUpgrade 12 → 19)"
description: "Generate an OpenUpgrade migration environment and run the checkpointing driver."
audience: [developer]
updated: 2026-09-25
---

# Migrating a database (OpenUpgrade 12 → 19)

The **migration** mode generates an [OpenUpgrade](https://github.com/OCA/OpenUpgrade) environment that upgrades
an Odoo Community database from an old version up to a current one. Migration is **sequential — no version
skips** (per OpenUpgrade): a 13 → 18 migration runs each of 14, 15, 16, 17, 18 in order.

```bash
python3 -m odoo_dwg migrate      # Generate a migration environment (asks source → target)
```

## The pages

In the order a migration is done:

1. [The migration environment](environment.md): what is generated, where code comes from, keeping the work.
2. [Taking in a client copy](intake.md): the client's dump, add-ons and configuration, audited before the chain.
3. [Working on a copy of production](production-copies.md): neutralising it, and keeping it from the outside.
4. [Rehearsing a migration](rehearsing.md): on demo data, and against a module built to break.
5. [Running a migration](running.md): preflight, the driver, hooks, repairs, following a run, the report.
6. [Checks and findings](checks-findings.md): `migrate audit`, and the findings ledger with the client's decisions.

## Cleaning up

The migration menu's **Clean a migration environment** action removes an environment directory
(venvs, configs, checkpoints, logs, requirements, driver) after preview and an exact-phrase
confirmation (`DELETE`) — use it to retest from scratch or clear leftovers. The findings ledger goes with
it, so when there is one the confirmation says so: copy `findings/` first if you still need the client's
decisions. Removing the shared
`.repos` clone cache is a separate opt-in (it serves *every* migration environment). The PostgreSQL
migration database is never touched; drop it manually (`dropdb -h 127.0.0.1 -U odoo migration_13_to_18`,
named after the chain) for a fully
clean run — the `-h`/`-U` are needed because the development role is trusted over loopback TCP, not over the
Unix socket.

## Scope & caveats

- A **full 12 → 19 run needs a real legacy dump** and is not part of automated tests; WSL acceptance covers
  environment generation, `uv` venv builds, `odoo-bin --version`, and `bash -n` on the driver.
- The `overrides-<ver>.txt` pins for the Python-3.10 steps (16.0/17.0) are validated against a real
  `uv pip install` on WSL. The 13 step runs the OpenUpgrade *fork's* own `odoo-bin` (those
  branches predate `--upgrade-path`/`openupgrade_framework`); the recipe launches and reaches the shared
  database (verified on WSL) but its migration semantics still await a real legacy dump.
- The tool needs **no container runtime at all**: every step, 13 included, runs in a `uv` virtualenv on the
  host.
- Migrating **custom module code** across versions is a separate job — see
  [`oca-port`](https://github.com/OCA/oca-port) and
  [`odoo-module-migrator`](https://github.com/OCA/odoo-module-migrator).

## Official references

- OpenUpgrade — running a migration: <https://oca.github.io/OpenUpgrade/040_run_migration.html>
- OpenUpgrade — introduction (sequential chaining): <https://oca.github.io/OpenUpgrade/010_introduction.html>
- openupgradelib: <https://github.com/OCA/openupgradelib>
- Odoo's own (Enterprise) upgrade platform, for contrast: <https://www.odoo.com/documentation/18.0/administration/upgrade.html>
