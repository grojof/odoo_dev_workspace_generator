---
type: how-to
title: "Migrating a database (OpenUpgrade 12 → 19)"
description: "Generate an OpenUpgrade migration environment and run the checkpointing driver."
audience: [developer]
updated: 2026-09-20
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
  module with this warning; the [staging workflow](#staging-custom-modules-menu--stage-custom-modules) prepares
  most of this mechanically.

## Staging custom modules (menu → Stage custom modules)

The heavy mechanical part of adapting **custom** module code is automated by orchestrating
[`odoo-module-migrator`](https://github.com/OCA/odoo-module-migrator) (OCA — the *code*-side complement
of OpenUpgrade, with migration scripts for every bump through 18.0→19.0):

1. You point at the directory holding your custom modules **at the source version** (never modified) and
   pick the modules.
2. Per chain step, the previous stage's code is copied into `addons/odoo<major>/custom/<module>` (a
   throwaway git worktree the tool creates for it) and the tool applies exactly that bump. Observed on
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

## Keeping the work: rehearse many times, run once

A real migration is rehearsed several times and run once against the client's latest dump. The rehearsals are
where the work happens — the migrator does what it can mechanically and you fix the rest, version by version
— and the final run should **apply** that, not derive it again.

The corrections live in the environment's `addons/odoo<major>/custom`, which **cleaning deletes** and
re-staging replaces. So when a version is reviewed, promote it.

**Menu → Migration → Promote reviewed modules** copies a module's code, for the steps you pick, to a
directory you name — one subdirectory per version:

```
~/odoo-acme/            # yours; the tool refuses a location inside ~/odoo-migrations
├── 13.0/client_sales/  # reviewed, for that version
├── 14.0/client_sales/
└── …
```

It **copies**, so the environment stays runnable and a promotion is not a point of no return. The throwaway
git repository that staging creates inside each stage directory is *not* copied — see below.

Then staging **consumes** it. Ask for the same directory when you stage, and a step whose code is already
promoted is taken as given, with **no migrator run for it**:

```
[3/6] Take client_sales stage 14.0 from the promoted copy … [OK]
```

The report says, per step, whether it was *derived* or *taken* — a step that was not derived is a step whose
warnings you will not see this run, and that is worth knowing. A chain with nothing promoted behaves exactly
as it did before.

### Divergence

Because promotion copies, the two can drift: you keep working in the environment, or you edit the promoted
copy directly. The staging report names it, comparing **content** (a `cp -a` and a `git checkout` both
preserve timestamps that say nothing about what the files hold):

```
| Step | Environment vs promoted |
| --- | --- |
| 13.0 | diverged |
| 14.0 | same |
```

Neither copy is authoritative. The report says they differ; you decide which is right.

### Git, and two repositories that are not the same thing

The promoted directory is yours. A git repository over it, **one branch per version**, is what we recommend:
`git diff 13.0..14.0` then answers "what did that hop change", and the target version's branch is what you
hand to the client — which is the only version that gets maintained afterwards.

Do not confuse it with the `.git` you will find inside each *stage* directory. `odoo-module-migrate` refuses
to run outside a repository, so staging creates a throwaway one there and commits the pre-migration state
into it with an identity, hook path and signing of its own — deliberately insulated from your global git
config, so that a mandatory signature or a global hook cannot fail the step. That history is scaffolding.
Yours is the promoted one, committed with your identity.

### Decisions about modules nobody will port

When a module resolves nowhere and OpenUpgrade declares no successor, the preflight names it and stops there.
What follows is a decision only you can make — dropped, replaced by another module, ported by us — and for
an **official or OCA** module that decision is the same for every client migrating between the same two
versions.

Record it once, in a file you own, and pass it to **Preflight check**:

```json
{
  "decisions": [
    {
      "module": "sale_x",
      "source": "12.0",
      "target": "18.0",
      "decision": "dropped",
      "reason": "no successor; the client stopped using it in 2024"
    }
  ]
}
```

Coverage then shows it as *Decided* instead of asking again, and reports what is still **undecided** as its
own class, separate from code that is simply not on disk.

A decision is **never believed over the sources**. The fates of Odoo and OCA modules are derived from that
step's checkout and `apriori.py` every time the question is asked — never frozen into this tool or into your
file — so when the sources say otherwise the decision is reported as stale and *not* applied:

```
WARN  Decision no longer holds (18.0)  sale_x was decided dropped — the module now resolves in this step's sources
```

That matters most for OCA, which ports modules continuously: a module recorded as dead a year ago may have a
branch today, and a frozen answer would keep a client on a workaround they no longer need.

### OCA repositories

Name them when you generate the environment and they are cloned per version into the shared cache and linked
into each step's `addons/odoo<major>/oca`, exactly as a workspace does. Without them that directory is filled
by hand, and whether a module is ported to a step's version — a fact the branch states — depends on whoever
last copied something in.

A repository OCA has **not** ported to one of your versions is reported for that step and does not fail the
generation: the branch is asked for before it is cloned, and its absence is a fact you need, not a reason to
refuse to build the environment.

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

The driver **works on a copy, never production**. Take a custom-format dump of the source database (plain
SQL dumps are rejected), copy its filestore, and hand the dump to the driver:

```bash
# On the source host — custom format (-Fc) is required:
pg_dump -Fc -h <source-host> -U <source-user> <source-db> -f source-13.0.dump

# The attachments live outside the database. Copy the source filestore to this
# host under the working database's name, or every ir_attachment row in the
# migrated database will point at a file that is not there:
rsync -a <source>/.local/share/Odoo/filestore/<source-db>/ \
      ~/.local/share/Odoo/filestore/migration_13_to_18/

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

**The working database.** Each environment upgrades **its own** database on the shared PostgreSQL, named
after its chain — `migration_13_to_18` for a 13 → 18 environment — which a fresh run drops and recreates
from the dump. Two *different* chains can therefore run at once; two runs of the *same* chain cannot, and
the second would drop the first's database. Nothing ever touches the source database.

A checkpoint is a `pg_dump` of that database — a full copy of whatever you restored, production data
included — and `logs/<version>.log` is Odoo's log for it. The driver keeps `checkpoints/` and `logs/`
at `700` and writes into them at `600`, so a second account on the host cannot read them. An environment
that predates that is narrowed the next time you generate over it: upgrading the tool alone changes
nothing already on disk.

Checkpoints that carry no record of which dump they came from stop the driver rather than let it resume
against a dump that may not be theirs; it prints the one command that adopts them if it is.

**When a step fails.** The driver names the step and its log (`[fail] step 16.0 failed — see
logs/16.0.log`). Read that log: the cause is usually one of your own modules under
`addons/odoo<major>/custom` that has not been adapted to that version. Fix it there, then run the same
command again — it resumes from the last checkpoint rather than from the source. Re-running without fixing
anything fails identically.

**When it finishes.** `[done] migration complete` leaves the result in the `migration_13_to_18` database on the
shared cluster. To look at it, start that step's Odoo by hand:

```bash
cd ~/odoo-migrations/13-to-18
.venv/odoo18/bin/python .repos/odoo-18.0/odoo-bin -c conf/odoo18.conf -d migration_13_to_18
```

To take it away: `pg_dump -Fc -h 127.0.0.1 -U odoo migration_13_to_18 -f migrated-18.0.dump` (and the filestore
directory alongside it).

**Resuming.** Run the same command again after a failure.
- **What it restores:** before the first step still missing, the driver restores the **newest checkpoint**
  into the working database. A failed step can leave that database half-migrated, because OpenUpgrade commits
  module by module, so it is never migrated again as it stands.
- **One source dump per run:** the first run records the dump's SHA-256 in `checkpoints/source.sha256`. A
  re-run with a different dump is refused, because the checkpoints belong to the first one. To start over
  from another dump, remove the whole `checkpoints/` directory — removing only some of it is what the driver
  is protecting you from.
- **Checkpoints with no recorded hash** — a `checkpoints/` directory that has dumps but no
  `source.sha256` — stop the driver, because it cannot tell whether they are this dump's. It prints the
  one command that adopts them if they are; remove the directory if they are not.

### What the run leaves behind, step by step

Besides each step's `logs/<version>.log`, the driver appends one line per event to `logs/steps.tsv`:

```
2026-09-20T11:32:51+02:00	a1b2c3d4e5f6	-	run-start	12.0 -> 18.0
2026-09-20T11:32:55+02:00	a1b2c3d4e5f6	13.0	start
2026-09-20T11:41:02+02:00	a1b2c3d4e5f6	13.0	ok
2026-09-20T11:41:05+02:00	a1b2c3d4e5f6	14.0	start
2026-09-20T11:49:00+02:00	a1b2c3d4e5f6	14.0	fail	1
```

The columns are *when*, *which run* (the source dump's hash, so several runs can share the file), *which
step*, *what happened* (`start`, `ok`, `fail`, `skip`, `restore`, `run-start`, `run-ok`) and a detail — the
exit code for a failure.

It is **appended and never rewritten**, so a run you interrupt still leaves a readable record, and it
accumulates across runs: the file is the history of every attempt on this chain.

Two things it is for. You can follow a run live:

```bash
tail -f ~/odoo-migrations/12-to-18/logs/steps.tsv      # where the chain is
tail -f ~/odoo-migrations/12-to-18/logs/14.0.log       # what that step is saying
```

And the timestamps are in the form `journalctl` takes, so a step's window can be handed to the firewall's
journal rather than guessed at — which is how you find out what a step tried to reach:

```bash
journalctl -t opensnitch --since "2026-09-20T11:41:05+02:00" --until "2026-09-20T11:49:00+02:00" \
  | grep odoo-bin
```

With the [outbound firewall](egress-control.md) installed, `odoo-bin` is rejected anywhere but localhost, so
anything in that window is a step reaching for the outside — worth knowing before that code reaches
production.

### Following a run while it happens

You start the driver by hand, and a 12 → 19 chain takes hours. **Menu → Migration → Follow a running
migration**, from another terminal, shows where it is:

```
Migration 12.0 → 19.0  (a1b2c3d4e5f6)
+------+-----------+---------+
| Step | State     | Elapsed |
+------+-----------+---------+
| 13.0 | ok        | 8m 07s  |
| 14.0 | ok        | 12m 31s |
| 15.0 | running   | 3m 12s  |
| 16.0 | pending   | —       |
+------+-----------+---------+

15.0 — worth reading so far
| WARNING | odoo.modules.loading  | 412 | sale_x: field removed |
| ERROR   | odoo.modules.registry | 1   | could not load sale_x |

Reached outside its own machine
  reject pypi.org ×3 (00-odwg-003-reject-odoo-external)
```

It only reads. **Ctrl-C stops watching; the driver keeps going** — it is another process. When the run ends
the watch says how, and points you at the report, because the live view follows the *running* step and so
its last frame holds no detail.

If you would rather not leave a terminal on it, the two files behind that view are plain text:

```bash
tail -f ~/odoo-migrations/12-to-19/logs/steps.tsv    # where the chain is
tail -f ~/odoo-migrations/12-to-19/logs/15.0.log     # what that step is saying
```

### The report: what happened, and what is still open

**Menu → Migration → Report on the runs so far** reads the step log, each step's Odoo log and the firewall's
journal, and writes `reports/report-<stamp>.md` into the environment. It is generated when you ask for it;
the history it reads from is what accumulates.

It opens with **Still open**, which is the part that matters:

```markdown
## Still open

- **Step 18.0 failed** — exit 1 — see …/logs/18.0.log
- **Step 17.0 passed with 3 error line(s)** — first: could not load sale_x
```

That second kind is the one worth having: a step can exit zero and still have logged errors, and "the chain
finished" is not the same as "nothing went wrong".

Then, per step of the latest run, its log summarised by what the lines actually carry — level, logger,
message and **how many times** it occurred:

```markdown
| Level | Logger | Count | First message |
| --- | --- | --- | --- |
| ERROR | `odoo.modules.registry` | 1 | could not load sale_x |
| WARNING | `odoo.modules.loading` | 412 | sale_x: field removed |
```

Counted rather than repeated: one broken field emits the same warning per record, and four hundred copies of
it would hide the error above. Nothing here tells you what a warning *means* — that is your judgement, and
inventing categories would be asserting something about OpenUpgrade this project has not verified.

And, where the firewall is installed, what the step reached for — asked of the journal **for that step's own
window**, and only for that step's process:

```markdown
**The step reached outside its own machine:**

- `reject` pypi.org ×3 (rule `00-odwg-003-reject-odoo-external`)
```

A step marked *skip* is shown as having run nothing that time, so its silence is not read as a clean run.

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
