---
type: how-to
title: "Migrating a database (OpenUpgrade 12 → 19)"
description: "Generate an OpenUpgrade migration environment and run the checkpointing driver."
audience: [developer]
updated: 2026-07-05
---

# Migrating a database (OpenUpgrade 12 → 19)

The **migration** mode generates an [OpenUpgrade](https://github.com/OCA/OpenUpgrade) environment that upgrades
an Odoo Community database from an old version up to a current one. Migration is **sequential — no version
skips** (per OpenUpgrade): a 13 → 18 migration runs each of 14, 15, 16, 17, 18 in order.

```bash
python3 -m odoo_dwg migrate      # Generate a migration environment (asks source → target)
```

## The interpreter problem (and how it is solved)

Each step runs the *target* version's `odoo-bin`, under a Python matched to that version. On Ubuntu 24.04 the
oldest interpreters are not natively installable. Measured on the WSL test box:

| Odoo step | Python | How it runs |
|-----------|--------|-------------|
| 14 / 15 | 3.8 | **`uv` native** (uv's installable floor is 3.8) |
| 16 / 17 | 3.10 | `uv` native |
| 18 / 19 | 3.12 | `uv` native |
| 13 | 3.6 | **Docker fallback** (`odoo:13.0`) — uv can't provide 3.6 |
| 12 | 3.5 | Docker fallback (`odoo:12.0`) if the source itself must run |

`uv`'s 3.8 ships a bundled OpenSSL, so it works where a source-built 3.6 (pyenv) fails against system OpenSSL 3.
**Because every step runs the target version, a source database ≥ 13 migrates entirely natively** — only a
12 → 13 step needs Docker. The `odoo:12.0`/`odoo:13.0` images are still pullable (verified). The generator only
emits the Docker recipe; your host provides the daemon.

## What is generated

Under `~/odoo-migrations/<src>-to-<tgt>/`:

- Per-version clones of `odoo/odoo` and `OCA/OpenUpgrade` (matching branch, shallow) in the shared
  `.repos/` cache.
- A `uv` virtualenv per native version (matched interpreter + `requirements.txt` + `psycopg2-binary` +
  `openupgradelib`), plus a per-version `requirements/overrides-<ver>.txt`.
- A per-step `conf/odoo<major>.conf` whose `addons_path` threads the OpenUpgrade `openupgrade_scripts`.
- `run_migration.sh` — the checkpointing driver.

## Running the migration

The driver **works on a copy, never production**. Give it a custom-format dump of the source database:

```bash
cd ~/odoo-migrations/13-to-18
bash run_migration.sh /path/to/source-13.0.dump
```

It restores the dump into a working database on the shared PostgreSQL, then runs each step with
`--update all --stop-after-init` (Odoo ≥ 14: `--load=base,web,openupgrade_framework`), and **`pg_dump`s a
checkpoint after each successful step** — so a failure resumes from the last good step, not from the source.

## Scope & caveats

- A **full 12 → 19 run needs a real legacy dump** and is not part of automated tests; WSL acceptance covers
  environment generation, `uv` venv builds, `odoo-bin --version`, and `bash -n` on the driver.
- The exact `overrides-<ver>.txt` pins and the 12/13 OpenUpgrade command layout are refined against real runs.
- Migrating **custom module code** across versions is a separate job — see
  [`oca-port`](https://github.com/OCA/oca-port) and
  [`odoo-module-migrator`](https://github.com/OCA/odoo-module-migrator).

## Official references

- OpenUpgrade — running a migration: <https://oca.github.io/OpenUpgrade/040_run_migration.html>
- OpenUpgrade — introduction (sequential chaining): <https://oca.github.io/OpenUpgrade/010_introduction.html>
- openupgradelib: <https://github.com/OCA/openupgradelib>
- Odoo's own (Enterprise) upgrade platform, for contrast: <https://www.odoo.com/documentation/18.0/administration/upgrade.html>
