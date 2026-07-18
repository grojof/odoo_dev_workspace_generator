# migration-environment Specification

## Purpose
TBD - created by archiving change add-openupgrade-migration. Update Purpose after archive.
## Requirements
### Requirement: Version-to-interpreter acquisition matrix

The system SHALL map each Odoo target version in a migration chain to a Python interpreter and an acquisition
method. For Odoo ≥ 14 the interpreter SHALL be provided natively by `uv` (whose installable floor is 3.8);
for Odoo 13 (Python 3.6) and Odoo 12 (Python 3.5), which `uv` cannot provide, the method SHALL be the Docker
fallback (official `odoo:13.0` / `odoo:12.0` images).

#### Scenario: Native uv interpreters for modern versions

- **WHEN** the matrix is queried for Odoo 14, 16, and 18
- **THEN** it returns a `uv`-native interpreter (e.g. 3.8, 3.10, 3.12 respectively), not a Docker fallback

#### Scenario: Docker fallback for Python-3.6/3.5 versions

- **WHEN** the matrix is queried for Odoo 13 (or 12)
- **THEN** it returns the Docker fallback method, because `uv` cannot install Python 3.6/3.5

### Requirement: Per-version clones from the shared cache

The system SHALL clone, for each target version in the chain, `odoo/odoo` and `OCA/OpenUpgrade` on the
matching version branch into the shared repo cache, reusing an existing clone rather than re-cloning.

#### Scenario: OpenUpgrade branch matches the Odoo version

- **WHEN** the environment is generated for a chain that includes version 16
- **THEN** the plan clones `OCA/OpenUpgrade` on branch `16.0` alongside `odoo/odoo` `16.0`, skipping any clone already present

### Requirement: Per-version uv virtualenv with repaired requirements

For each natively-run version the system SHALL create a virtualenv with `uv` using the matched interpreter and
install that version's `requirements.txt` with a per-version `overrides-<ver>.txt` applied via
`uv pip install --overrides` (lifting pins that no longer install for the matched interpreter — e.g. the
16.0/17.0 branches' `gevent==21.8.0` for Python 3.10 exactly, lifted to the branches' own 3.11 pins), plus
`psycopg2-binary` and `openupgradelib`. A completed venv SHALL be stamped with a ready marker; generation
SHALL skip on the marker (not on the venv directory) so an interrupted build is redone, not silently skipped.

#### Scenario: A modern step's venv is built with the matched interpreter

- **WHEN** the environment is generated for a step running Odoo 14
- **THEN** the plan builds the venv with `uv venv --python 3.8` and installs requirements plus the overrides and `openupgradelib`

#### Scenario: A half-built venv is rebuilt on the next generation

- **WHEN** a previous generation was interrupted after creating a venv but before its installs finished
- **THEN** the next generation rebuilds that venv (its ready marker is absent) instead of skipping it

### Requirement: Per-step migration config

The system SHALL write a per-step `odoo.conf` whose `addons_path` includes the target version's Odoo add-ons
and the OpenUpgrade `openupgrade_scripts`, and whose database connection targets the shared migration cluster.

#### Scenario: Config includes the OpenUpgrade scripts path

- **WHEN** the per-step config for version 18 is rendered
- **THEN** its `addons_path` references the `openupgrade_scripts` directory of the OpenUpgrade 18.0 checkout

### Requirement: Migration environment cleanup

The system SHALL offer a cleanup action that removes an existing migration environment directory (venvs,
configs, checkpoints, logs, requirements, driver) through the standard plan → preview → apply flow, gated by
an exact-phrase confirmation. Removing the shared clones cache SHALL be a separate opt-in within the same
plan, and the PostgreSQL migration database SHALL NOT be touched by the plan.

#### Scenario: A leftover environment is removed after preview and confirmation

- **WHEN** the operator picks an existing environment to clean and confirms with the exact phrase
- **THEN** the previewed plan removes that environment's directory and nothing else

#### Scenario: The shared clones cache is only removed on explicit opt-in

- **WHEN** the operator declines the shared-cache option
- **THEN** the plan contains no command touching the shared `.repos` cache

