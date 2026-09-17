# Spec Delta

## REMOVED Requirements

### Requirement: Version-to-interpreter acquisition matrix

**Reason**: The requirement was built around two acquisition methods, a native interpreter and a container
image, and its scenarios asserted the container path for Odoo 12/13. That path is gone: the Odoo 13 step runs
on a `uv`-provided Python 3.8 like every other step, and Odoo 12 is never executed by a chain at all.

**Migration**: Replaced by "Native interpreter per chain step" below, which keeps the override behaviour
unchanged and drops only what described the container.

## ADDED Requirements

### Requirement: Native interpreter per chain step

The system SHALL map each Odoo target version in a migration chain to a Python interpreter, taken from the
support matrix's recommendation for that version. Every step SHALL run natively in a `uv`-provided
virtualenv; no step SHALL depend on a container image. Odoo 13 runs on `uv`'s installable floor (3.8), which
is above its documented minimum and is what makes a container unnecessary.

The recommendation SHALL be a default the operator can override on any step of the chain: an overridden step
uses the chosen interpreter while every other step keeps its recommendation. An override SHALL be validated
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

## MODIFIED Requirements

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
directory) so an interrupted build is redone, not silently skipped.

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

### Requirement: Generation runs the host preflight first

`Generate a migration environment` SHALL run the chain-scoped host preflight before planning and show its
table. MISSING chain-required tools SHALL NOT hard-block generation (the plan itself may be unaffected) but
SHALL require an explicit confirmation to continue.

#### Scenario: A missing tool prompts before generating

- **WHEN** the operator generates a 12 → 18 environment on a host without `uv`
- **THEN** the preflight table shows it MISSING and generation continues only after the operator confirms
