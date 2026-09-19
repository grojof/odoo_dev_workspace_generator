## MODIFIED Requirements

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
