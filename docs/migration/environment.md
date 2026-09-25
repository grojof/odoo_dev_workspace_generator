---
type: how-to
title: "The migration environment"
description: "What a migration environment is made of: interpreters, generated files, OpenUpgrade layouts, coverage, add-ons, staging, git and decisions."
tags: [migration, environment, interpreters, staging]
audience: [developer]
updated: 2026-09-25
---

# The migration environment

What `python3 -m odoo_dwg migrate` generates, where each piece of code comes from, and how the work is
kept between rehearsals. The flow as a whole is in [Migrating a database](README.md).

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

These interpreters are the **recommendations** the [support matrix](../reference/support-matrix.md) declares per version —
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
  patched core. A regeneration offers what the generated steps already run, and says so when that is not
  the client's core. It matters because every step installs the modules whose `auto_install` dependencies are
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
