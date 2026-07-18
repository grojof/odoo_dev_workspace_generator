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
  `openupgradelib`). A per-version `requirements/overrides-<ver>.txt` is applied via
  `uv pip install --overrides` to repair pins that no longer install: the 16.0/17.0 branches pin
  `gevent==21.8.0` for Python 3.10 exactly, which has no cp310 wheel and whose sdist no longer compiles
  under modern Cython — the overrides lift those steps to the branches' own 3.11 pins
  (`gevent==22.10.2` + `greenlet==2.0.2`, validated on WSL). Each finished venv is stamped with a
  `.odwg-ready` marker; a generation interrupted mid-install rebuilds that venv on the next run
  (`uv venv --clear`) instead of skipping it half-built.
- Per-version addons directories — `addons/odoo<major>/custom` and `addons/odoo<major>/oca` — threaded
  into each step's `addons_path` ahead of OpenUpgrade and core (operator code wins module lookup).
- A per-step `conf/odoo<major>.conf` whose `addons_path` composes custom → OCA → the OpenUpgrade
  checkout → core.
- `run_migration.sh` — the checkpointing driver, with a built-in preflight.

## Where your addons go

The database being migrated almost certainly has OCA and custom modules installed. Every step must be
able to *find* every installed module, or it is left broken mid-chain:

- **OCA modules** — clone/copy each OCA module's **published branch for that version** into
  `addons/odoo<major>/oca/<module>` (e.g. the 16.0 branch of `partner-contact` modules under
  `addons/odoo16/oca/`).
- **Custom modules** — place each module's **migrated code for that version** in
  `addons/odoo<major>/custom/<module>`. Presence is necessary but *not sufficient*: the code must be
  adapted to each version's breaking changes (e.g. 17.0 removes view `attrs`/`states`; 18.0 renames
  `<tree>` to `<list>`) and may need its own `migrations/` scripts. The preflight flags every custom
  module with this warning; the staging workflow (see the `add-custom-module-staging` change) prepares
  most of this mechanically.

## Staging custom modules (menu → Stage custom modules)

The heavy mechanical part of adapting **custom** module code is automated by orchestrating
[`odoo-module-migrator`](https://github.com/OCA/odoo-module-migrator) (OCA — the *code*-side complement
of OpenUpgrade, with migration scripts for every bump through 18.0→19.0):

1. You point at the directory holding your custom modules **at the source version** (never modified) and
   pick the modules.
2. Per chain step, the previous stage's code is copied into `addons/odoo<major>/custom/<module>` (a
   throwaway git worktree — the tool requires one) and the tool applies exactly that bump. Observed on
   WSL with `odoo-module-migrator==0.5.0`: 18.0 converts `<tree>` → `<list>` and bumps the manifest
   version per step; some changes (e.g. the 17.0 view-`attrs` removal) are *not* auto-applied by this
   tool version and remain review work — which the candidate findings and the tool's own WARN/ERROR
   lines point at. Its full output is captured per step.
3. The staged code is then cross-referenced against the step's OpenUpgrade **analysis files**
   (`upgrade_analysis.txt`, already in the cloned checkouts): references to core fields/models **removed**
   in that step are reported as *candidate* findings with file and line. Candidates need your
   confirmation — a name match is a lead, not proof (generic names like `name`/`state` are not text-matched).
4. For steps with findings, an **inert scaffold** `migrations/<ver>.1.0.0/pre-migration.py` is written
   (openupgradelib import + one TODO per finding). If your module already has that file, the scaffold
   lands beside it as `pre-migration.generated.py` — your code is never overwritten.
5. Everything ends in `staging/report-<module>.md`: tool log verbatim, findings, scaffolds. **Staging is a
   prepared starting point; your review completes the migration** — the tool never marks a module migrated.

The tool itself installs into a shared uv venv (`~/odoo-migrations/.tools/module-migrator`) through a
previewed plan the first time you stage.

## Preflight: verify before you burn hours

**Menu → Migration → Preflight check** runs a read-only verification, and the same checks run
automatically when generating an environment (host scope) and inside the driver (both scopes):

| Scope | Checks |
|-------|--------|
| Host | `uv`; Docker binary + daemon + `odoo:12.0`/`odoo:13.0` images (only when the chain has a 12/13 step); PostgreSQL reachable + dev role; the dump exists and `pg_restore --list` parses it (which also enforces the required custom format, `pg_dump -Fc` — plain SQL dumps are rejected); addons layout present |
| Database | actual source version from `ir_module_module` (`base`) vs. the declared source; installed-module list; **per-step coverage** — every installed module must resolve in every step's `addons_path`, and each miss names the exact directory to fill |

The database scope needs a live database: name an already-restored one in the menu action, or let the
driver verify right after its initial restore (it aborts before step 1 on any failure). Docker-step
coverage (12/13) is reported as not verifiable — the official image provides core.

## Running the migration

The driver **works on a copy, never production**. Give it a custom-format dump of the source database:

```bash
cd ~/odoo-migrations/13-to-18
bash run_migration.sh /path/to/source-13.0.dump
```

It preflights the host, restores the dump into a working database on the shared PostgreSQL, verifies the
database (version match, addons coverage) before step 1, then runs each step with
`--update all --stop-after-init` (Odoo ≥ 14: `--load=base,web,openupgrade_framework`), and **`pg_dump`s a
checkpoint after each successful step** — so a failure resumes from the last good step, not from the source.
Any preflight failure exits non-zero with a `[preflight-fail]` line naming the check.

## Cleaning up

The migration menu's **Clean a migration environment** action removes an environment directory
(venvs, configs, checkpoints, logs, requirements, driver) after preview and an exact-phrase
confirmation (`DELETE`) — use it to retest from scratch or clear leftovers. Removing the shared
`.repos` clone cache is a separate opt-in (it serves *every* migration environment). The PostgreSQL
migration database is never touched; drop it manually (`dropdb`) for a fully clean run.

## Scope & caveats

- A **full 12 → 19 run needs a real legacy dump** and is not part of automated tests; WSL acceptance covers
  environment generation, `uv` venv builds, `odoo-bin --version`, and `bash -n` on the driver.
- The `overrides-<ver>.txt` pins for the Python-3.10 steps (16.0/17.0) are validated against a real
  `uv pip install` on WSL. The 12/13 Docker step runs the OpenUpgrade *fork's* own `odoo-bin` (those
  branches predate `--upgrade-path`/`openupgrade_framework`); the recipe launches and reaches the shared
  database (verified on WSL) but its migration semantics still await a real legacy dump.
- Docker for the 12/13 steps means **Docker Engine inside the Linux host itself** (installed by
  `provision apply` as `docker.io`) — not Docker Desktop integration from Windows.
- Migrating **custom module code** across versions is a separate job — see
  [`oca-port`](https://github.com/OCA/oca-port) and
  [`odoo-module-migrator`](https://github.com/OCA/odoo-module-migrator).

## Official references

- OpenUpgrade — running a migration: <https://oca.github.io/OpenUpgrade/040_run_migration.html>
- OpenUpgrade — introduction (sequential chaining): <https://oca.github.io/OpenUpgrade/010_introduction.html>
- openupgradelib: <https://github.com/OCA/openupgradelib>
- Odoo's own (Enterprise) upgrade platform, for contrast: <https://www.odoo.com/documentation/18.0/administration/upgrade.html>
