---
type: how-to
title: "Migrating a database (OpenUpgrade 12 → 19)"
description: "Generate an OpenUpgrade migration environment and run the checkpointing driver."
audience: [developer]
updated: 2026-09-19
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
| 13 | 3.8 | `uv` native (above its 3.6 floor; the branch installs and runs there) |
| 12 | — | never executed: the chain restores it and migrates away from it |

These interpreters are the **recommendations** the [support matrix](support-matrix.md) declares per version —
what this project has built and run — not the only ones each version accepts. Before planning, the generate
flow shows one row per chain step and lets you **pin any step** to a specific Python; the rest keep their
recommendation. A pinned step's `overrides-<ver>.txt` repair follows the interpreter actually in use, and an
out-of-range choice is stated (range, chosen version, evidence tier) before it is accepted. Every step can be
pinned, including 13.

**Every step runs natively**; the tool needs no container runtime. The Odoo 13 step used to run in the official
`odoo:13.0` image, and that was a mistake worth recording: the image's `odoo.conf` sets
`addons_path = /mnt/extra-addons`, so the mounted fork's `odoo-bin` loaded the *image's* add-ons and every
add-on migration script was skipped while the step still reported success. Running it natively — and naming
the add-ons path explicitly — fixes that.

The 13 step needs two repairs the modern ones do not: `setuptools<58` as a **build** constraint (its
`vatnumber==1.2` still calls `use_2to3`) and `setuptools<81` installed (Odoo ≤ 16 imports `pkg_resources`).
Both are generated for you in `requirements/`.

## What is generated

Under `~/odoo-migrations/<src>-to-<tgt>/`:

- Per-version clones of `OCA/OpenUpgrade` (matching branch, shallow) in the shared `.repos/` cache. From
  14.0 there is also a clone of `odoo/odoo`. Up to 13.0 the OpenUpgrade branch is itself a full Odoo fork, so
  no separate clone is made.
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

## Two OpenUpgrade layouts

Up to 13, the OpenUpgrade checkout **is** a full Odoo fork and each add-on carries its own
`migrations/<version>/` scripts; the step runs the fork's `odoo-bin` with a config whose `addons_path` names
the fork's `addons` directory, and there is no `--upgrade-path` or `openupgrade_framework`. From 14 the checkout
is an add-on collection beside a separate Odoo clone, with scripts under `openupgrade_scripts/scripts`
reached via `--upgrade-path`. The generated per-step `odoo.conf` states the path explicitly in both cases,
because a defaulted or inherited path is exactly how the container version went wrong.

## What the coverage check blocks on

Before the first step, the preflight lists every module installed in the source database and asks whether each
step of the chain can resolve it. A long chain is full of core modules Odoo renamed, merged or deleted, so
"not found" alone would refuse almost every real migration. The check therefore:

1. **Resolves what OpenUpgrade declares.** Each step's checkout carries `openupgrade_scripts/apriori.py` with
   its `renamed_modules` and `merged_modules`; a module whose declared successor exists in that step is
   covered. This is why `web_editor` does not block a 12 → 19 chain — 19.0 declares it renamed to
   `html_editor`.
2. **Splits the rest by author.** A module authored by Odoo that no step provides and no rename accounts for
   is Odoo's own dropped code: it is reported as a **warning**, and the upgrade uninstalls it. Anything else
   — your modules, OCA, a vendor's — is **blocking**, and the report names the module, the step and the exact
   `addons/odoo<major>/custom` directory to fill.

The driver applies the same rule and refuses only on the blocking class. The author test is an exact match on
Odoo's own spellings, never a substring: OCA modules are authored "Odoo Community Association (OCA)", and
treating those as Odoo's would wave through exactly the code whose absence breaks a step.

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
automatically when generating an environment (host scope) and inside the driver — its four host checks
(everything in the Host row below except the addons layout, which only the menu and generate flows check)
plus the whole database scope:

| Scope | Checks |
|-------|--------|
| Host | `uv` (every step's interpreter); PostgreSQL reachable + dev role; the dump exists and `pg_restore --list` parses it (which also enforces the required custom format, `pg_dump -Fc` — plain SQL dumps are rejected); addons layout present |
| Database | actual source version from `ir_module_module` (`base`) vs. the declared source; installed-module list; **per-step coverage** — every installed module must resolve in every step's `addons_path`, and each miss names the exact directory to fill |

The database scope needs a live database: name an already-restored one in the menu action, or let the
driver verify right after its initial restore (it aborts before step 1 on any failure). For a ≤ 13 step,
coverage looks in the OpenUpgrade fork itself: its `addons` and `odoo/addons`, and its renames in
`odoo/addons/openupgrade_records/lib/apriori.py`.

## Running the migration

The driver **works on a copy, never production**. Give it a custom-format dump of the source database:

```bash
cd ~/odoo-migrations/13-to-18
bash run_migration.sh /path/to/source-13.0.dump
```

It preflights the host, restores the dump into a working database on the shared PostgreSQL, verifies the
database (version match, addons coverage) before step 1, then runs each step with
`--update all --stop-after-init` (Odoo ≥ 14: `--load=base,web,openupgrade_framework`), and **`pg_dump`s a
checkpoint after each successful step**. Any preflight failure exits non-zero with a `[preflight-fail]` line
naming the check. A `[fail]` line is the driver's own abort: a checkpoint that cannot be written, a step
whose `odoo-bin` failed (it names the step's log file), a step whose OpenUpgrade code is not on disk — Odoo
would migrate nothing and say nothing in that case, so the driver checks before running it — or checkpoints
that came from a different source dump.

**The working database.** Every environment upgrades a database called `migration` on the shared PostgreSQL,
which a fresh run drops and recreates from the dump. Two environments therefore cannot run at the same time,
and a previous run's database is replaced. Nothing ever touches the source database.

**Resuming.** Run the same command again after a failure.
- **What it restores:** before the first step still missing, the driver restores the **newest checkpoint**
  into the working database. A failed step can leave that database half-migrated, because OpenUpgrade commits
  module by module, so it is never migrated again as it stands.
- **One source dump per run:** the first run records the dump's SHA-256 in `checkpoints/source.sha256`. A
  re-run with a different dump is refused, because the checkpoints belong to the first one. To start over
  from another dump, remove the whole `checkpoints/` directory — removing only some of it is what the driver
  is protecting you from.
- **Checkpoints from 0.1.0** have no recorded hash, so a driver generated by 0.2.0 refuses them. Remove
  `checkpoints/` and run the chain again.

### Keeping a migration from reaching the outside

Each step's `odoo.conf` sends mail to the local capture (`127.0.0.1:1025`). With the
[outbound firewall](egress-control.md) installed, every `odoo-bin` step is also rejected on any non-local
connection, and each attempt is logged.
- **Rehearsing on a copy:** also run **Redirect a database's mail to Mailpit** on it, so that its own mail
  servers do not bypass `odoo.conf`.
- **A database going back to production:** do **not** redirect it. Keep the firewall on during the run, and
  review what it tried to reach before cutover ([live production migrations](egress-control.md#live-production-migrations)).

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
