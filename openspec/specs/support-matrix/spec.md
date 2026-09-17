# support-matrix Specification

## Purpose

Declares, in one authoritative and evidence-tiered place, what the tool supports — which Linux hosts, which
Python the tool itself needs, and per Odoo version the Python range, the recommended interpreter and the
PostgreSQL minimum — so every other surface derives its support statements from that declaration instead of
restating them, and so each bound can be traced to an official source and re-verified on demand.

## Requirements

### Requirement: Single authoritative support matrix

The system SHALL declare exactly one support matrix as pure data, covering: the supported host operating
system releases, the minimum Python the tool itself runs on, and — for every Odoo version the tool handles —
the minimum Python, the maximum Python, the recommended interpreter, and the minimum PostgreSQL. No other
module SHALL declare a competing bound for any of these facts.

#### Scenario: Every supported Odoo version has a complete row

- **WHEN** the matrix is queried for each Odoo version the tool handles
- **THEN** each version yields a minimum Python, a maximum Python, a recommended interpreter and a minimum
  PostgreSQL, with no gaps

#### Scenario: A version outside the matrix is rejected, not guessed

- **WHEN** the matrix is queried for an Odoo version it does not declare
- **THEN** the lookup reports the version as unsupported rather than falling back to a default bound

### Requirement: Every bound carries its evidence tier and source

Each bound in the matrix SHALL carry an evidence tier — `official` (stated by Odoo or the distribution),
`derived` (deduced from an official artifact, such as the newest interpreter bucket declared in a branch's
`requirements.txt`), or `untested` (no source states it and the tool has not validated it) — together with
the source it came from. Operator-facing output and documentation SHALL NOT present a `derived` or
`untested` bound as an official requirement.

#### Scenario: A derived maximum is not presented as official

- **WHEN** a Python maximum whose tier is `derived` is shown to the operator or rendered into documentation
- **THEN** it is labelled as derived, with its source, and is not described as an Odoo requirement

#### Scenario: An untested bound is visible as such

- **WHEN** the matrix is queried for a version whose Python maximum no source states
- **THEN** the bound's tier is `untested` and any output carrying it says so

### Requirement: Support statements derive from the matrix

Every operator-facing surface that states a support bound — host readiness reporting, workspace generation,
migration environment generation, and the generated per-workspace README — SHALL read it from the matrix.
Changing a bound in the matrix SHALL change every one of those surfaces without editing them.

#### Scenario: A changed bound propagates without touching surfaces

- **WHEN** a version's minimum PostgreSQL is changed in the matrix
- **THEN** host readiness reporting and the generated documentation report the new floor, with no other
  module edited

### Requirement: Recommended interpreter is a default, not a mandate

The matrix SHALL mark one interpreter per Odoo version as recommended, and every flow that builds an
environment SHALL use it as the default while letting the operator choose a different interpreter. An
operator-chosen interpreter SHALL be validated against that version's Python range and refused only when the
operator declines to proceed after being shown the conflict.

#### Scenario: Operator keeps the recommendation

- **WHEN** an environment is built and the operator makes no interpreter choice
- **THEN** the recommended interpreter for that version is used

#### Scenario: Operator chooses another in-range interpreter

- **WHEN** the operator selects an interpreter that is inside the version's declared Python range
- **THEN** the plan uses the chosen interpreter without a warning

#### Scenario: Operator choice outside the range is shown before it is used

- **WHEN** the operator selects an interpreter outside the version's declared Python range
- **THEN** the flow states the range, the chosen version and the evidence tier of the bound being crossed,
  and proceeds only on explicit confirmation

### Requirement: The matrix is re-verifiable against its sources

The project SHALL document the procedure that produced each bound — the source URLs, the order of
precedence between them, and the known traps in retrieving them — and SHALL provide a check that re-derives
the matrix from those sources and reports any drift against the declared data. The check SHALL never mutate
the declared matrix and SHALL NOT be imported by the package at runtime.

#### Scenario: Drift against an official source is reported

- **WHEN** the check runs and an Odoo version's declared minimum Python disagrees with that version's
  official source
- **THEN** the check reports the disagreement, naming the version, both values and the source URL, and exits
  non-zero

#### Scenario: A matching matrix reports no drift

- **WHEN** the check runs and every declared bound agrees with its source
- **THEN** it reports no drift and exits zero, leaving the declared matrix untouched
