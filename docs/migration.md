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
  14.0 there is also a clone of the **chain core**, `odoo/odoo` (`.repos/odoo-<version>`) or `OCA/OCB`
  (`.repos/ocb-<version>`). Up to 13.0 the OpenUpgrade branch is itself a full Odoo fork, so no separate
  clone is made.
- **Which core the steps from 14.0 run on.** Generation asks, and the default is the core the intake
  identified: a client on OCB is migrated on OCB, and official Odoo is the default with no intake or with a
  patched core. It matters because every step installs the modules whose `auto_install` dependencies are
  met, and OCB turns `auto_install` off for a list of them (17 at 18.0: `iap`, `sms`, `partner_autocomplete`,
  `mail_bot`, `base_import_module`, `account_edi_ubl_cii`…). A client on OCB migrated on official Odoo ends
  up with modules it never had, and they stay installed if the core is switched later. Otherwise the two
  cores are the same code, module versions and schema, so switching a running database between them is a
  code change, not a migration. The choice is recorded only in the step configs' `addons_path`, and every
  later action reads it back from there. OpenUpgrade's own CI tests on `odoo/odoo` only; OCA tests its
  modules on both.
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

**After a client intake, generation proposes the list.** It offers every repository the intake's
availability check found an installed module in, at any step of the chain, together with those already
linked. That includes the repositories modules move into later, such as `bank-statement-import`, where a
core bank statement import module lives from 14.0. You may edit the list. Every later action (the
preflight, the report, the module fates) reads the linked repositories back from each step's
`addons/odoo<major>/oca`, so they are never asked for twice.

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

**What the chain installs by itself.** A step installs modules the source never had: dependencies an
upgraded module now declares, then `auto_install` glue modules. OpenUpgrade's 13.0 loader and its
framework from 18.0 install every glue module whose requirements are met; between them Odoo installs one
only when something it needs is new. The preflight reads which rule each step's checkout applies,
lists the modules as *Installed by the chain (13.0)*, and checks them at every later step. A dependency
no source has is a **MISSING** row. When the intake's cached OCA trees have it, the preflight names the
repository to add (`account_statement_base (16.0): OCA has it in account-reconcile`).

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

### When the client's data breaks a migration script: step hooks

A migration script can meet data it does not expect. The first client's 14.0 step stopped because
OpenUpgrade gives every bank statement line a journal entry, and some lines belonged to closed banks
whose accounts were deprecated. What to do is a decision about the client's data, so it is yours, in
the environment:

- `hooks/<version>-pre.sql` runs before that step;
- `hooks/<version>-post.sql` runs after the step succeeds, and before its checkpoint, so the checkpoint
  holds what the post-step hook restored.

Each file runs in one transaction and stops at its first error. The driver prints `[hook] 14.0 pre: …`
and records it in `logs/steps.tsv`. A failing hook stops the run before the step. Keep a pre-step change
reversible and have the post-step hook undo exactly it. For example, record which deprecated accounts
you make usable in a table of your own, and deprecate exactly those again. Record the decision in the
findings ledger too.

### A known OpenUpgrade 14.0 defect the driver repairs: statement lines stored as reconciled

For a source up to 13.0, OpenUpgrade's 14.0 account post-migration gives every bank statement line
without an entry one, through the ORM (`fill_statement_lines_with_no_move`). It then computes the lines'
`is_reconciled` and `amount_residual` in raw SQL (`fill_account_bank_statement_line_reconciliation`). There
is no flush in between. The ORM still holds the values it computed while each move had no suspense line
yet (`is_reconciled = True`), and a later flush writes them over the SQL result.

A line still waiting in the suspense account then reads as reconciled, and the reconciliation screen,
which filters on that field, hides it. How many lines are hit depends on how many pending values the ORM
still holds when the script ends: on the first client's copy it was part of such lines in one run and
all of them in another.

The driver repairs it right after the 14.0 step and its post hook, before the checkpoint. It selects in
SQL the only lines the defect can leave wrong: stored as reconciled while their move still has a line on
the journal's suspense account. It then recomputes them in `odoo-bin shell` on the 14.0 Odoo with Odoo's
own `_compute_is_reconciled` (the same rule as in 18.0), prints how many it selected and how many are
still reconciled, and records `repair` in `logs/steps.tsv`. Only those lines go through the ORM, so it
takes seconds on a large database, and it selects nothing once OpenUpgrade flushes itself
([OCA/OpenUpgrade#6005](https://github.com/OCA/OpenUpgrade/pull/6005)).

### A known OCA defect the same repair covers: the SII certificate file

Up to 13.0, `l10n_es_aeat_sii` keeps the AEAT certificate (the `.p12`) in a column of its own table. The
14.0 migration of `l10n_es_aeat_sii_oca` creates one `l10n.es.aeat.certificate` per old record, but it
moves attachments only, so the file never reaches the new model. The same run of the 14.0 repair carries
each file from the old table, through OpenUpgrade's legacy link, when the new certificate has none, and
records `repair sii-certificate-file`. The keys are files on the old server's disk: on the new server,
open each certificate and obtain the keys again with its password.

### When a module has no code anywhere: `decisions.json`

Coverage stops a run when an installed module resolves in no source of a step and OpenUpgrade declares no
successor for it. That is not a bug to work around — it is a question only you can answer, and it happens
for real: OCA ported `website_sale_product_attribute_filter_category` to 14.0, 15.0, 17.0 and 18.0 but
**not** to 16.0 or 19.0.

Record the answer in the environment's own `decisions.json`:

```json
{
  "decisions": [
    {
      "module": "website_sale_product_attribute_filter_category",
      "source": "12.0", "target": "19.0",
      "decision": "dropped",
      "reason": "OCA has not ported it to 16.0 or 19.0 (present in 14, 15, 17, 18)",
      "evidence": {"checked": "2026-09-20"}
    }
  ]
}
```

Both readings honour it — the preflight action *and* the driver, which is the one that stops the run — and
a decision is matched under **any name the module carries in the chain**, since a rename does not make it a
different module. An applied decision is always named in the output with its reason, never applied
silently:

```
[coverage] website_sale_product_attribute_filter_category: dropped for 16.0 — as you recorded (OCA has not
ported it to 16.0 or 19.0)
```

**A decision is never believed over the sources.** It is applied only while the module still resolves
nowhere and still has no successor that does; when either changes — OCA ports it, OpenUpgrade declares a
successor — the preflight reports the decision as **stale** instead of applying it. A file that cannot be
read decides nothing, so a typo cannot open the gate.

The file is the operator's, carried between clients: the fates of Odoo and OCA modules are facts the tool
derives every time, and this records the one thing no source states.

### Rehearsing before there is a client dump

The driver needs a source dump, and before a client's database exists nobody has one. **Menu → Migration →
Seed a demo source database** builds one from Odoo's own demo data.

It prepares the **source** version, which the chain itself never builds — `chain()` is 13.0 … 19.0 for a
12 → 19 migration, so the environment has no Odoo 12 clone, venv or config at all. It needs none to
migrate; it needs one to *make* a dump. What it builds is plain Odoo, not OpenUpgrade: there is no
OpenUpgrade 12.0 branch, and the 12 → 13 step runs OpenUpgrade 13.

Before asking what to install, it shows what this chain does to the modules already linked under the
source version's `addons/odoo12/oca` and `custom`:

```
[INFO] Modules found under the source version, with what this chain does to them:
  website_sale_product_style_badge             absorbed into website_sale (14.0)
  account_consolidation                        renamed to account_consolidation_oca (14.0)
  partner_firstname                            carries on under its own name
```

That is the set worth rehearsing with — **one absorbed, one renamed, one that carries on** — because those
are three different things for the chain to get right, and they are read from each step's own `apriori.py`,
not chosen by this tool's opinion. Only modules actually on disk at the source version are offered: one
that is not there cannot be installed there, and a rehearsal that fails for that reason reads exactly like
the chain failing.

Applying the plan writes `seed_demo.sh`. Run it yourself, like the driver:

```bash
cd ~/odoo-migrations/12-to-19
./seed_demo.sh                      # builds seed_12 with demo data, dumps it
./run_migration.sh source-12.0-demo.dump
```

It installs **one module per call**, so a failure names which module rather than saying that something did
not install, and it stops there instead of dumping a database missing the module the rehearsal was for. It
refuses to overwrite an existing dump or reuse an existing database — a dump the checkpoints were taken
against is not replaceable silently.

Demo data is loaded because the flag is *not* passed: in Odoo 12.0 to 18.0 `--without-demo` defaults to
off, so a database created with `-i` gets demo data. (19.0 rewrote that option and flipped the default,
which cannot affect a seed — a chain's source is always ≤ 18.0.)

**Menu → Migration → Module fates in this chain** answers the same question for any module you name,
without seeding anything: renamed to X at a step, absorbed into Y at a step, or nothing declared, which
means it is expected to carry on. A step whose `apriori.py` cannot be read is named as unread rather than
counted as declaring nothing.

### Rehearsing against a module built to break

A chain rehearsed only against the client's own add-ons exercises the classes of change *that client*
happens to meet. **Menu → Migration → Generate the migration tester** writes an add-on of the tool's own
into every step's `addons/odoo<major>/custom`, with one probe per class of change the chain actually
contains — taken from that chain's own `upgrade_analysis.txt` files and `apriori.py`, never invented:

```
23 probes, from this chain's own sources.
  16.0  removed_model      base.update.translations
  16.0  unstored_field     sale.order/show_update_pricelist
  16.0  moved_field        account.move/partner_shipping_id
  ...
[WARN] Classes this chain never exercises: company_dependent
```

The classes with no instance are named rather than dropped: a class with no probe is not a class that
passed.

Each probe is a **declaration**, not synthesized model code — a record naming the subject, the class, the
step its analysis predicts it at, and that file's own line. (Generated model code referring to the subject
would fail on the *source* version when derived wrongly, destroying the rehearsal instead of measuring it.)

After a step, **Check the migration tester** asks the database what became of each subject, by reading its
`ir_model` and `ir_model_fields`. It needs no Odoo running, which is the point: the step worth asking about
is often the one where something failed to load.

```
[WARN] 2 probe(s) need looking at in acme_16.
  ! 16.0  gone unannounced   moved_field: account.move/partner_shipping_id
      sale / account.move / partner_shipping_id (many2one): module is now 'account' ('sale')
  ! 16.0  still there        removed_model: base.update.translations
      obsolete model base.update.translations [transient]
    16.0  intact             unstored_field: sale.order/show_update_pricelist
```

The two findings come first, and they are the two the run's logs never mention:

- **gone unannounced** — the subject is not there and nothing predicted it would go. This is the quiet
  loss: the module loaded, the step passed, and a column is empty.
- **still there** — the sources said it would go and it did not, so a migration script did not run.

The others are printed too, one line each, so you can see the question was asked:

- **`intact`** — the subject is still there and nothing said it would go.
- **`gone as predicted`** — it went, and what it became is there instead.
- **`not yet reached`** — the probe is about a step this database has not reached, so its subject being
  present says nothing yet. Expect many of these when checking between steps.
- **`past its step`** — the database is beyond the probe's step, so a missing subject cannot be blamed on
  it.
- **`not observed`** — neither the subject nor its successor is in the database, so this probe measured
  nothing: the subject was never installed here. It sorts **last**, after everything that was actually
  measured, and is not counted as a pass. A real run reported two module probes as `gone as predicted`
  about modules that had never been installed — absent proves nothing on its own.

If the module never installed, every probe reports `absent` rather than a reassuring `intact`.

**A module the chain installs along the way.** The preflight reads the source database once, so it cannot
see a module that does not exist yet: `partner_firstname_portal` appeared in an OCA repository at 18.0, was
auto-installed there because its dependencies were present, and had vanished from that repository by 19.0 —
installed, with no code, and nothing had asked. Each step therefore re-reads the live database and judges
what the preflight never saw, stopping at the step that found it rather than at the end.

**A probe can only report a loss if there was something to lose.** A field whose *model* is not in the
database, a module whose successor is not there either — neither was ever present, so the probe measured
nothing and says `not observed`. A real 12 → 19 run produced four alarms at one step about `stock.quant`
and `purchase.order` in a database where neither module was installed.

**Check after each step, not only at the end.** A probe claims something about *its own* step — *at 15.0
this field stops being computed, so it should survive that step*. A database carried on to 19.0 has had
four more steps at it, and a subject a later step removed is not a silent loss at 15.0. Checking a 12 → 19
chain only at the end produced six such false alarms, and six on seven steps teach you to stop reading the
report. Where the database is past a probe's step, a missing subject is reported as **`past its step`**
rather than as a finding — run the check between steps to judge those. An expected removal is still judged
from any later version, because "gone from its step onward" holds there too.

**What `not observed` cannot catch.** It fires when the subject *and* its successor are both missing. Where
the successor is a core module that would be installed anyway — `base_vat_sanitized` is absorbed into
`base_vat`, which any accounting database has — its presence says nothing about whether the subject was
ever there, and the probe still reads `gone as predicted`. Module probes are therefore only as meaningful
as the module set you seeded: probe what you installed.

The tester is a rehearsal instrument. Its manifest says so, it depends on `base` alone, and it declares no
menu, no group, no `auto_install` and read-only access to its own table.

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

Each step's `odoo.conf` sends mail to the local capture (`127.0.0.1:1025`) and runs no cron thread. With
the [outbound firewall](egress-control.md) installed, every `odoo-bin` step is also rejected on any non-local
connection, and each attempt is logged.

**The driver neutralises the working database**
([neutralisation](egress-control.md#neutralising-a-copy-of-production)) at three points:
- after restoring the source dump;
- after every successful step, before that step's checkpoint;
- after restoring a checkpoint to resume.

It then checks that nothing can act, and stops the run if something still can. Every checkpoint, and the
migrated database, is therefore neutralised. Re-applying after each step matters because a step's module
updates switch crons back on by themselves. Each neutralisation is a `neutralised` line in `steps.tsv`.

Generating the environment writes `neutralise.sql` and `neutralise_check.sql` beside the driver. An
environment generated before this has neither: the driver then warns that the database is **not**
neutralised, and regenerating adds them.

**The driver never gives production's settings back.** That is **Give a neutralised database its
production settings back**, run by you, on the day of the cutover
([how](egress-control.md#giving-production-its-settings-back)). Keep the firewall on during the run, and
review what it tried to reach before cutover
([live production migrations](egress-control.md#live-production-migrations)).

### Opening a migrated database for testing

Open a migrated database, or a checkpoint you restored, only through the environment's own script:

```bash
~/odoo-migrations/12-to-18/open_for_testing.sh 18.0 migration_12_to_18
```

On every start it does three things, in order:
1. **Neutralises the database again.** This covers anything an install or update switched back on since
   the last start.
2. **Runs the check.** If anything can still act on the outside, it refuses to start and names what.
3. **Starts that version's Odoo** on `http://127.0.0.1:8069`, with **no cron thread**, loopback only, and
   mail sent to the capture.

With no cron thread, a cron that a module you install during the session creates or reactivates cannot
run before the next start turns it off. There is no option to skip either guard.

## Taking in a client copy

A client hands over three things: a database dump, an archive of the add-ons their server loads, and
its `odoo.conf`. Often a filestore archive comes too. **Menu → Migration → Take in a client copy** works
through them in steps. Each step is previewed and confirmed. Each writes what it found into the
environment's `intake.json`, its data tables into `findings/data/intake-*.tsv`, and its findings into the
[findings ledger](#recording-what-the-migration-finds). Findings are recorded as `internal`: the
client-facing text is yours to write.

| Step | What it does | What it guards against |
|---|---|---|
| Restore the client's dump | Into a new **reference** database, `--no-owner --no-acl`, errors kept in `findings/data/intake-restore.stderr`. Tables restored are counted against the dump's table of contents. | An existing database is refused. Every `pg_restore` error is classified against a list of known, data-safe classes, each with its reason and source. The first is an aggregate on `array_cat(anyarray)`, which [PostgreSQL 14 changed](https://www.postgresql.org/docs/release/14.0/). An error of no known class is a high-severity finding. |
| Create the read-only role | `SELECT` only (on sequences too: a wizard leaves no rows, so its id sequence is the only trace it was used; `nextval` is still refused), read-only by default, no `TEMP`, and no access to secret columns: passwords, tokens, keys, `ir_config_parameter.value`, attachment contents. Tables holding one are granted column by column. | Column existence is read from `pg_attribute`: `information_schema` hides columns by privilege. The random password is generated in the command, handed to PostgreSQL on standard input and written only to `~/.pgpass` (mode 600), never shown. |
| Unpack the client's add-ons archive | Into `client-src/`, then made read-only. | An existing directory is refused. |
| Classify the add-ons archive | Maps the client's `addons_path` onto the archive and finds the core. Per repository it records the remote, commit, commits ahead of and behind upstream, and uncommitted files. Per installed module it records where it loads from. | Both manifest names count (`__openerp__.py` too), and the first directory in the client's order wins. Everything is read from the delivered `.git` only, and the client's remotes are never contacted. Credentials in a remote URL are removed before anything is recorded. |
| Identify the client's core | Official Odoo or OCA/OCB, and the exact commit. It samples trees of both histories, refines between the best sample's neighbours, and looks up the files that still differ in both histories, merge commits included. A file found in neither is a **local patch**. | Histories are blobless clones in `.repos/history/` (trees, no file contents), because shallow build clones have no history. Files only the client has, like a stray `.xml_backup`, are reported apart. |
| Unpack the client's filestore | Into `data/filestore/<reference>`, whatever the archive's top level. | An existing target is refused. |
| Build the client's source | The core cloned at its commit into `.repos/<flavour>-<version>-<commit>`, with a venv and a source `odoo.conf` whose `addons_path` is the client's directories in the client's order, then the core's, with `data_dir` in the environment. The Python packages the installed modules declare (`external_dependencies`) are installed too; classification records them, mapping import names to pip names (`OpenSSL` → `pyOpenSSL`). | Pinned: the directory carries the commit, and nothing moves it. The modules' packages are installed **held to what the venv already has**: a module listing `lxml` unpinned once upgraded it past what Odoo 12 imports. A package that would need an upgrade fails the step by name. |
| Copy the reference to a working database | `createdb -T <reference> <copy>`, phrase `COPY`. | The reference itself is never opened. |
| Survey what the copy can act on | Reads the reference as its owner. Each armed neutralisation rule becomes a finding, ranked by the severity the catalogue declares (tax and EDI critical, crons high, IAP medium…). Also records the overdue crons, queued jobs by channel and state, and the mail queue. Failed mail that a retry would send is a finding of its own. | Reads only. A role that cannot read a column gets "could not tell", never "clean". |
| Check each installed module along the chain | Follows every installed Odoo and OCA module through each step's OpenUpgrade fate, and finds its code at each step: the core, then the client's OCA repositories. For the steps where gaps remain, it looks in **every** OCA repository, listed from GitHub's API. Gaps, and modules that moved repository, become findings; custom modules are listed to port. | OCA trees are blobless, one-commit clones cached in `.repos/oca-trees/`. A missing branch leaves an `.absent` marker; a network failure stops the step instead of being taken for one. |
| Scan the client's own code for network calls | Every installed module that is neither Odoo's nor OCA's, for `requests`, `urllib`, `smtplib`, `ftplib`, `paramiko`, `zeep`, sockets, processes, RPC, job-queue delays and Odoo's IAP client; `tests/` and `migrations/` skipped. | Every pattern must first match its own control line, or no result is reported. "No pattern matched" is not "safe". |
| Audit the client's own modules | Reads the reference only. For every module the intake classified as the client's own, plus any you name, it records the evidence for deciding whether to drop, replace or port it: the installed modules that depend on it; each model it created, with its rows and rows written since a date you give (a wizard: times opened, from its id sequence); each stored field it created, with the rows holding a value (`false` and `''` are not values), those written since the date, and the last write; its many2many links; its documents (in the Print menu? registered under another module's namespace, a trap when that module updates? attachments named as it names its PDF); and whether OCA publishes a module of that name at the target. Given a migrated database, it checks each field and table survived; given a web access log (Odoo's or a proxy's), it counts prints per document since the date. Each module is labelled *in use*, *in use, undated*, *not used since*, or *no data*. | Odoo records no print, and a production log at `log_level = warn` records no request: only a proxy's access log says what is printed. Files a module's code writes as attachments, rather than through a document, are not attributed to it. The label is evidence; what the module does, and whether 18 covers it, is read from its code. |
| Find bank statement lines imported twice | For a source up to 13.0, where a statement line never reconciled has no entry: OpenUpgrade's 14.0 step gives every such line one (bank against suspense), with no switch ([OCA/OpenUpgrade#3056](https://github.com/OCA/OpenUpgrade/issues/3056)), so a statement imported twice becomes bank movements that never happened. Reads the reference only. A statement is trusted when its opening balance plus its lines equals its closing balance, both from the bank's file. A day that two trusted statements of one journal hold with the same lines and the same end-of-day balance is one bank day imported twice. Of each movement's copies one is kept (a reconciled one if any); each other unreconciled copy is a **duplicate**, each other reconciled copy a movement **reconciled twice**. Also counts the unreconciled lines, and those after the company's lock date. Writes `findings/data/bank-duplicate-lines.tsv`, a guarded `bank-duplicate-lines.sql` and one finding. It also lists the unreconciled lines dated on or before the later of the company's fiscal-year and period lock dates, other than the duplicates, in `bank-locked-unreconciled.tsv`: the file to deliver if the client's accountant decides not to carry closed periods' lines into the new version. A line whose exact amount matches an open receivable or payable item of the same partner is marked kept: it may be money never registered. `bank-locked-unreconciled.sql` leaves the others behind, still guarded (no journal item, still in a closed period), and is **optional**: it goes in the hook only on the accountant's decision. It also shortens the 14.0 step, which spends most of its time giving those lines entries. | Matching amount, date and label is not proof: two equal fees on one day are two movements. Repeats the balances cannot prove are not listed. It deletes nothing. The SQL deletes a line only while no journal item points at it and its kept twin still has the same content, so it is idempotent. Put it in the first step's pre hook (`hooks/<first step>-pre.sql`), which runs on the working copy, and re-run the step on the final copy. A movement reconciled twice is already in the books twice: the client's accountant corrects it. The Norma 43 import sets no `unique_import_id`, which is how a repeated file goes unnoticed. |
| Find journal codes the target refuses | Reads the reference only. Per company, the journals that share a code, and those whose codes differ only by case or surrounding spaces. In each group the journal with most entries keeps its code; every other gets a proposed code of 1 to 5 letters or digits, unique in the company. Writes `findings/data/journal-codes.tsv`, a guarded `journal-codes.sql` and one finding. | Odoo declares `unique (company_id, code)`. From 15.0 each step drops it and adds it again; with a shared code it only logs `unable to add constraint`, and the migrated database keeps no constraint. Edit the `proposed` column (a bank and brand code reads better than a generated one) and run the step again: it keeps your codes and refuses, by name, one that is not 1 to 5 letters or digits or not unique. The table also takes a code for **any** other journal, the one that keeps a group's code included, for a readable scheme (for instance, bank journals by company and age). That is optional: Odoo 18 names a new entry after the journal's last entry, so a renamed journal with history keeps its numbering, but anything that selects journals by code (an accountant's export) needs the table as its equivalence. A code equal to the current one renames nothing, and a code another journal holds now is refused, since the guarded SQL renames one journal at a time. The SQL changes only `account_journal.code`, so no sequence and no existing entry number moves, and only while the journal still has its old code and the new one is free. Put it in the first step's pre hook. |
| Rehearse uninstalling modules on a copy | For modules with no code at some step of the chain. OpenUpgrade documents no procedure for them; its maintainers leave it to the operator to port the module's scripts or uninstall it ([OCA/OpenUpgrade#5336](https://github.com/OCA/OpenUpgrade/issues/5336)). An uninstall deletes what the module owns, drops its tables and columns with `CASCADE`, and uninstalls its dependents, so this step shows what it takes on the client's data. It clones a **neutralised** working copy to a throwaway database with a hard-linked filestore, uninstalls there through the source version's `odoo-bin shell` (the Apps screen's own call), then neutralises and checks the throwaway database. Every table of the two databases is then compared by exact row count and columns. Each difference is named **module data** (owned through `ir_model_data`, reloaded on reinstall), **wizard**, **metadata**, **recomputed** (a related column), **empty**, or **data lost**. | The working copy is never modified, so a dropped column's values are counted where it still exists. Refuses the reference, a copy that is not neutralised, a module that is not installed, and an existing throwaway name; phrase `REHEARSE`. A table that lost more rows than the modules owned is data lost, a cascade included. The finding is `high` when anything is. The throwaway database is left for inspection. |

The source instance is then opened like any other version, through the guarded start:

```bash
~/odoo-migrations/12-to-18/open_for_testing.sh 12.0 acme_copy
```

With an intake, the guarded start:
- **refuses the reference database by name**;
- **gives a copy its own filestore on first start**, as hard links to the reference's. That takes no
  space, and Odoo never rewrites an attachment file in place, so the reference's files stay as they were;
- **uses the environment's `data_dir`** for every version, so a migrated database finds the client's
  attachments too.

The chain carries the same `data_dir`: every step's configuration names it. Before the first step, and
after any resume from a checkpoint, the driver gives its working database a filestore of hard links to the
reference's (`[filestore] … hard links to …`).

Each step's venv also needs what the client's modules declare in `external_dependencies`, at that
step's version. After generating with an intake, the tool lists them per step and offers to install
them, held to what each venv has. Before each step the driver checks them with that step's interpreter,
as Odoo would, and stops naming the module and the library (`[python] … needs … for 13.0: not
installed`) instead of failing minutes into the step.

## Recording what the migration finds

A client migration finds things long before it runs a step: a tax-reporting module in production mode with
invoices pending, crons that would all fire at start, mail that has not left for years, a core that is OCB
rather than official Odoo. Each finding is recorded once, in the environment's **findings
ledger**, and the reports shown to the client are rendered from that ledger only. A report is never edited
by hand: correct the ledger and render the report again.

```text
~/odoo-migrations/12-to-18/
├── findings/
│   ├── findings.json      # the ledger
│   └── data/*.tsv         # the tables findings cite (first row is the header)
└── reports/
    ├── findings-client.<lang>.md     # for the client
    └── findings-extended.<lang>.md   # everything, and how to check it
```

### What a finding carries

Every finding carries the following, and one without its evidence or its query is refused:

| Field | Holds |
|---|---|
| `id` | A kebab-case id, unique; a withdrawn finding's id is never reused |
| `severity` | `critical`, `high`, `medium`, `low` or `info` |
| `audience` | `client` or `internal`; an internal finding never reaches the client report |
| `evidence` | The structured facts it rests on |
| `query` | The command or SQL that re-derives it |
| `action` | The proposed action |
| `decision` | `pending`, `accepted`, `act` or `declined`, with date and note; earlier decisions stay in `history` |

The query is mandatory because a figure quoted from memory, rather than re-derived, is how a report ends up
telling a client something that is not so.

A finding written for the client also carries a `client` block **per language**: `{"es": {"title", "text",
"question", "level"}}`. A table it attaches is `{"file", "audience", "title", "columns", "note"}`:
- `columns` relabels the header per language;
- `note` is printed under the table.

Values are printed verbatim. If a table goes to a client, write its values the way the client reads them
(`No enviada`, not `not_sent`), in a file of its own per language.

Text meant for a reader is either a plain string or `{"en": …, "es": …}`. This covers phase titles, what
was received, the versions, how the client's data is handled, and the reference links.

### Changing it, and reading it

Everything that writes the ledger or the reports is in **Menu → Migration → Findings and client reports**,
previewed and confirmed:
- start a ledger;
- add findings from a JSON file;
- record a decision;
- set a phase's state;
- withdraw a finding;
- write the reports.

A withdrawn finding moves to the **corrections** log with its reason. It disappears from the findings and
appears in the extended report's corrections, because a report that once showed a false finding must be
able to answer for it.

Reading it writes nothing:

```bash
odoo-dwg migrate findings list     --source 12.0 --target 18.0   # exit 1 while a decision is pending
odoo-dwg migrate findings show ID  --source 12.0 --target 18.0
odoo-dwg migrate findings validate --source 12.0 --target 18.0
odoo-dwg migrate findings report   --source 12.0 --target 18.0 --report-lang es [--kind extended]
odoo-dwg migrate findings links    --source 12.0 --target 18.0
```

`--report-lang` is the report's language and `--lang` the interface's. They are independent: an English
session can render a Spanish client report, byte-for-byte the same as a Spanish session would. A client
finding with no text in the requested language stops the report and is named. It is never replaced by the
technical summary, which is not written for the client.

`links` requests every **reference** link: the context, the client texts, and table titles and notes. It
never requests a URL recorded as evidence, in a summary or in a query. Those are the client's own systems,
and its first version sent a request to a client's production server that way.

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
