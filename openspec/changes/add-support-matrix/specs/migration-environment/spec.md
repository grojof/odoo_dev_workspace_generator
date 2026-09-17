# Spec Delta

## MODIFIED Requirements

### Requirement: Version-to-interpreter acquisition matrix

The system SHALL map each Odoo target version in a migration chain to a Python interpreter and an acquisition
method, taking the interpreter from the support matrix's recommendation for that version. For Odoo ≥ 14 the
interpreter SHALL be provided natively by `uv` (whose installable floor is 3.8); for Odoo 13 (Python 3.6) and
Odoo 12 (Python 3.5), which `uv` cannot provide, the method SHALL be the Docker fallback (official
`odoo:13.0` / `odoo:12.0` images).

The recommendation SHALL be a default the operator can override on any step of the chain: an overridden step
uses the chosen interpreter while every other step keeps its recommendation. An override SHALL be validated
against that version's declared Python range and, when outside it, used only after the flow has stated the
range, the chosen version and the bound's evidence tier and the operator has confirmed. An override SHALL be
refused for a version outside the chain, and for a Docker-fallback step, whose interpreter comes from the
official image.

A chain's steps are its *target* versions — the source version is restored, never run — so there is no
source-version interpreter to pin here; rehearsing a client's own environment for the version they run is
the dev workspace's job.

#### Scenario: Native uv interpreters for modern versions

- **WHEN** the matrix is queried for Odoo 14, 16, and 18
- **THEN** it returns a `uv`-native interpreter (e.g. 3.8, 3.10, 3.12 respectively), not a Docker fallback

#### Scenario: Docker fallback for Python-3.6/3.5 versions

- **WHEN** the matrix is queried for Odoo 13 (or 12)
- **THEN** it returns the Docker fallback method, because `uv` cannot install Python 3.6/3.5

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

#### Scenario: Override refused for a Docker-fallback step

- **WHEN** the operator tries to override the interpreter of an Odoo 12 or 13 step
- **THEN** the flow refuses, explaining that the interpreter of a Docker-fallback step is fixed by the
  official image
