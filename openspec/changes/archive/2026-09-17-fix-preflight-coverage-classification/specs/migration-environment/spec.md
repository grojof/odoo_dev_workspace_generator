# Spec Delta

## MODIFIED Requirements

### Requirement: Per-version uv virtualenv with repaired requirements

For each natively-run version the system SHALL create a virtualenv with `uv` using the matched interpreter and
install that version's `requirements.txt` with a per-version `overrides-<ver>.txt` applied via
`uv pip install --overrides` (lifting pins that no longer install for the matched interpreter — e.g. the
16.0/17.0 branches' `gevent==21.8.0` for Python 3.10 exactly, lifted to the branches' own 3.11 pins), plus
`psycopg2-binary` and `openupgradelib`.

For versions whose Odoo code imports `pkg_resources` at startup (Odoo ≤ 16), the venv SHALL also install a
`setuptools` release that still provides it. Nothing declares that dependency — `setuptools` arrives only
transitively, and which release it resolves to depends on the step's interpreter, so a step can start or fail
on that accident alone. It SHALL be pinned rather than left to resolution.

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
