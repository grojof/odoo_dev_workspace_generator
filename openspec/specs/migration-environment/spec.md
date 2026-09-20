# migration-environment Specification

## Purpose

Generates a self-contained OpenUpgrade environment for a source → target chain: per-version clones, a virtual environment per step on an interpreter that step supports, per-step configs, and the driver that runs them in order.

## Requirements

### Requirement: Per-version clones from the shared cache

The system SHALL clone, for each target version in the chain, `OCA/OpenUpgrade` on the matching version
branch into the shared repo cache, and `odoo/odoo` too from 14.0 on, reusing an existing clone rather than
re-cloning. A step up to 13.0 clones no separate Odoo: its OpenUpgrade branch is a full Odoo fork.

The chain's source and target SHALL be validated as supported `NN.0` versions before anything is planned,
because both reach the generated driver.

#### Scenario: OpenUpgrade branch matches the Odoo version

- **WHEN** the environment is generated for a chain that includes version 16
- **THEN** the plan clones `OCA/OpenUpgrade` on branch `16.0` alongside `odoo/odoo` `16.0`, skipping any clone already present

#### Scenario: A legacy step clones only the fork

- **WHEN** the environment is generated for a chain that includes version 13
- **THEN** the plan clones `OCA/OpenUpgrade` `13.0` and no `odoo/odoo` `13.0`

#### Scenario: A source or target with shell syntax is refused

- **WHEN** the operator enters `13.0$(curl …)` or `13` as the source
- **THEN** generation stops with an invalid-version error and nothing is written

### Requirement: Per-version uv virtualenv with repaired requirements

For each version in the chain the system SHALL create a virtualenv with `uv` using the matched interpreter and
install that version's `requirements.txt` with a per-version `overrides-<ver>.txt` applied via
`uv pip install --overrides` (lifting pins that no longer install for the matched interpreter — e.g. the
16.0/17.0 branches' `gevent==21.8.0` for Python 3.10 exactly, lifted to the branches' own 3.11 pins), plus
`psycopg2-binary` and `openupgradelib`.

Where a version's dependencies cannot be *built* by a current toolchain, the system SHALL also write a
per-version `constraints-<ver>.txt` and apply it with `uv pip install --build-constraints`, constraining the
build environment rather than the installed set — the 13.0 branch needs `setuptools<58` because
`vatnumber==1.2` still uses `use_2to3`, which setuptools 58 removed. A version needing no such repair SHALL
NOT get a constraints file.

For versions whose Odoo code imports `pkg_resources` at startup (Odoo ≤ 16), the venv SHALL also install a
`setuptools` release that still provides it.

A completed venv SHALL be stamped with a ready marker; generation SHALL skip on the marker (not on the venv
directory) so an interrupted build is redone, not silently skipped. A ready venv whose `pyvenv.cfg` names
another interpreter than the step now resolves to SHALL be rebuilt, so a newly pinned interpreter takes
effect; when `pyvenv.cfg` cannot be read, the ready venv is kept.

#### Scenario: A modern step's venv is built with the matched interpreter

- **WHEN** the environment is generated for a step running Odoo 14
- **THEN** the plan builds the venv with `uv venv --python 3.8` and installs requirements plus the overrides and `openupgradelib`

#### Scenario: A half-built venv is rebuilt on the next generation

- **WHEN** a previous generation was interrupted after creating a venv but before its installs finished
- **THEN** the next generation rebuilds that venv (its ready marker is absent) instead of skipping it

#### Scenario: A pkg_resources-era step pins setuptools

- **WHEN** the environment is generated for a step running Odoo 16
- **THEN** that venv's install includes a `setuptools` constrained to a release that still ships
  `pkg_resources`, so the step's `odoo-bin` starts instead of failing on import

#### Scenario: A step that does not need it is left alone

- **WHEN** the environment is generated for a step running Odoo 18
- **THEN** no `setuptools` constraint is added, because that branch does not import `pkg_resources`

#### Scenario: The 13.0 step carries build constraints

- **WHEN** the environment is generated for a chain that includes the Odoo 13 step
- **THEN** a `constraints-13.0.txt` is written pinning `setuptools<58`, and the requirements install applies
  it with `--build-constraints`, so the branch's `use_2to3` dependency builds instead of failing

#### Scenario: A newly pinned interpreter rebuilds a ready venv

- **WHEN** a step's venv was built on 3.10 and the operator now pins that step to 3.12
- **THEN** the next generation rebuilds that venv with 3.12 instead of skipping it on its ready marker

### Requirement: Per-step migration config

An existing generated file that would change SHALL first be copied to `<file>.bak-<date>`, stamped finely
enough that two runs in the same second cannot share a name and overwrite each other's backup, as the
workspace surface does: a step's config is where an operator adds `limit_time_real = 0` or an extra addons path while
chasing a failure, and re-generating an environment is routine.

The system SHALL write a per-step `odoo.conf` whose `addons_path` includes the step's per-version custom and
OCA directories, the OpenUpgrade checkout root (14.0 and later) or the fork's `addons` (13.0 and earlier), and
the target version's Odoo add-ons, and whose database connection targets the shared migration cluster.

A step's config SHALL set `workers = 0` and `max_cron_threads = 0`: the step runs threaded so a failure
is debuggable, and no scheduled action fires against what is a restored copy of a production database.

#### Scenario: A hand-tuned step config is kept

- **WHEN** an environment whose `conf/odoo17.conf` was edited by hand is generated again
- **THEN** the plan copies it to `conf/odoo17.conf.bak-<date>` before writing the new one

#### Scenario: Config includes the OpenUpgrade checkout

- **WHEN** the per-step config for version 18 is rendered
- **THEN** its `addons_path` references the root of the OpenUpgrade 18.0 checkout, from which
  `openupgrade_framework` and `openupgrade_scripts` both resolve

#### Scenario: No scheduled action runs against the restored database

- **WHEN** the per-step config for version 17 is rendered
- **THEN** it sets `max_cron_threads = 0`, so restoring a customer's database cannot fire its crons

### Requirement: Migration environment cleanup

The system SHALL offer a cleanup action that removes an existing migration environment directory (venvs,
configs, checkpoints, logs, requirements, driver, **and the per-version addons directories with whatever
custom or staged code they hold, and the staging reports**) through the standard plan → preview → apply
flow, gated by an exact-phrase confirmation. The confirmation SHALL name the staged modules among what
is about to go, since that code may carry the operator's own edits and exists nowhere else. Removing the shared clones cache SHALL be a separate opt-in within the same
plan, and the PostgreSQL migration database SHALL NOT be touched by the plan.

#### Scenario: A leftover environment is removed after preview and confirmation

- **WHEN** the operator picks an existing environment to clean and confirms with the exact phrase
- **THEN** the previewed plan removes that environment's directory and nothing else

#### Scenario: The shared clones cache is only removed on explicit opt-in

- **WHEN** the operator declines the shared-cache option
- **THEN** the plan contains no command touching the shared `.repos` cache

#### Scenario: The operator is told that staged code goes with it

- **WHEN** the operator picks an environment that holds staged custom modules
- **THEN** the confirmation names them as part of what will be deleted, before the phrase is asked for

### Requirement: Per-version custom and OCA addons layout

The migration environment SHALL define, for each target version in the chain, `addons/odoo<major>/custom`
and `addons/odoo<major>/oca` directories under the environment root, create them during generation, and
thread them into that step's `addons_path` ahead of OpenUpgrade and core (operator code takes precedence in
module lookup). The generated documentation SHALL state that the operator places each module's *migrated
branch* for that version there.

#### Scenario: Step config includes the per-version addons dirs

- **WHEN** the per-step config for version 16 is rendered
- **THEN** its `addons_path` lists `addons/odoo16/custom` and `addons/odoo16/oca` before the OpenUpgrade and core entries

### Requirement: Generation runs the host preflight first

`Generate a migration environment` SHALL run the chain-scoped host preflight before planning and show its
table. MISSING chain-required tools SHALL NOT hard-block generation (the plan itself may be unaffected) but
SHALL require an explicit confirmation to continue.

#### Scenario: A missing tool prompts before generating

- **WHEN** the operator generates a 12 → 18 environment on a host without `uv`
- **THEN** the preflight table shows it MISSING and generation continues only after the operator confirms

### Requirement: Native interpreter per chain step

The system SHALL map each Odoo target version in a migration chain to a Python interpreter, taken from the
support matrix's recommendation for that version. Every step SHALL run natively in a `uv`-provided
virtualenv; no step SHALL depend on a container image. Odoo 13 runs on `uv`'s installable floor (3.8), which
is above its documented minimum and is what makes a container unnecessary.

The recommendation SHALL be a default the operator can override on any step of the chain: an overridden step
uses the chosen interpreter while every other step keeps its recommendation. An override SHALL be a `3.N` version, and SHALL be validated
against that version's declared Python range and, when outside it, used only after the flow has stated the
range, the chosen version and the bound's evidence tier and the operator has confirmed. An override SHALL be
refused for a version outside the chain.

A chain's steps are its *target* versions — the source version is restored, never run — so there is no
source-version interpreter to pin here; rehearsing a client's own environment for the version they run is
the dev workspace's job.

#### Scenario: Every step resolves to a uv interpreter

- **WHEN** the matrix is queried for Odoo 13, 14, 16, and 18
- **THEN** each returns a `uv`-native interpreter (3.8 for 13 and 14, 3.10 for 16, 3.12 for 18) and none
  returns a container fallback

#### Scenario: One step pinned, the rest left on their recommendation

- **WHEN** the operator pins one chain step to a specific Python version that is inside that step's declared
  range
- **THEN** that step's venv is built with the chosen interpreter, its requirements repair follows that
  interpreter rather than the recommended one, every other step keeps its recommendation, and the preview
  names the interpreter per step

#### Scenario: Override refused for a version outside the chain

- **WHEN** the operator tries to pin a version that is not a step in this chain
- **THEN** the flow refuses, naming the chain's steps

#### Scenario: Override outside the declared range is confirmed first

- **WHEN** an override falls outside that version's declared Python range
- **THEN** the flow states the range, the chosen version and the bound's evidence tier, and applies the
  override only on explicit confirmation

#### Scenario: A malformed override is refused

- **WHEN** the operator pins a step to `3.x` or `3.10; rm -rf ~`
- **THEN** the flow refuses it as an invalid Python version and pins nothing

#### Scenario: A venv built with another interpreter is named before the preview

- **WHEN** a step's venv on disk was built with an interpreter other than the one this run resolves
- **THEN** the interpreter table names both, before the plan is previewed — a pin is not persisted, so
  this is the only warning that re-generating would rebuild that venv on something else

### Requirement: Migration steps send mail to the local capture

Each migration step's generated `odoo.conf` SHALL set `smtp_server = 127.0.0.1` and `smtp_port = 1025`.

#### Scenario: SMTP keys in a step config

- **WHEN** the step config for `17.0` is rendered
- **THEN** it contains `smtp_server = 127.0.0.1` and `smtp_port = 1025`

### Requirement: A migration environment may name OCA repositories

`addons/odoo<major>/oca` is created empty for the operator to fill by hand, so whether an OCA module is
ported to a step's version cannot be derived — only guessed, by whoever last copied something in. That is a
derivable fact answered by hand, and a hand answer about someone else's code ages without saying so.

A migration environment SHALL accept a list of OCA repositories, validated as the workspace surface
validates them. Generation SHALL clone each one per chain version into the shared cache and link it under
that step's `addons/odoo<major>/oca`, exactly as the workspace surface does, so a step resolves an OCA
module from the branch that OCA publishes for that version.

A repository with no branch for a version SHALL be reported for that step and SHALL NOT fail the
generation: a module OCA has not ported is a fact the operator needs, not a reason to refuse to build the
environment. An environment naming no repositories SHALL behave exactly as one does today.

#### Scenario: An OCA module resolves from its own version branch

- **WHEN** an environment names `server-tools` and is generated for a 12 → 18 chain
- **THEN** each step's `addons/odoo<major>/oca` links that repository's branch for that version, and
  coverage resolves its modules from there

#### Scenario: A repository not ported to a version is named, not fatal

- **WHEN** a named repository has no branch for 18.0
- **THEN** generation reports that step as having no OCA source for it and completes

### Requirement: A source database can be seeded from demo data

A rehearsal requires a source dump, which before a client's database exists nobody has. The system SHALL be
able to build a database at the chain's **source** version, with Odoo's demo data and a chosen set of
modules, and to dump it in the format the driver requires (`pg_dump -Fc`) into the environment, so that the
chain can then be run exactly as it would be on a client's dump.

The action SHALL refuse to overwrite an existing source dump without the operator saying so, because the
dump a chain's checkpoints were taken against is not replaceable silently.

Module installation SHALL be reported per module: a module that fails to install SHALL be named, and SHALL
NOT leave the action reporting a seeded database.

A module name given by the operator MUST be a valid Odoo module name before it reaches a command line;
otherwise the action SHALL stop naming the value.

#### Scenario: A chain rehearsed with no client data

- **WHEN** the operator seeds a 12.0 source database with demo data and runs the driver against the dump it
  produced
- **THEN** the chain runs as it would on a client's dump, through the same checkpoints

#### Scenario: A module that will not install

- **WHEN** one of the chosen modules fails to install at the source version
- **THEN** it is named and the action does not report a seeded database

#### Scenario: An existing dump is not replaced by accident

- **WHEN** the environment already holds a source dump
- **THEN** the action says so and does not overwrite it unless the operator confirms
