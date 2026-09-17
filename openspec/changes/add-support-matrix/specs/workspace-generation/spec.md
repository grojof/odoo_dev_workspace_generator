# Spec Delta

## MODIFIED Requirements

### Requirement: Per-instance virtual environment

The system SHALL create one virtual environment per instance at `.venv/odoo<major>` and install that version's
dependencies from the cloned repo's `requirements.txt`. The venv creation and installation SHALL run only as
part of an applied plan, never during file generation.

The interpreter each venv is built with SHALL be resolved against the support matrix before the plan is
assembled. When the host `python3` is inside that version's declared Python range it SHALL be the default.
When it is outside the range, the flow SHALL state the range, the detected host version and the evidence tier
of the bound being crossed, and offer to build that venv with a matching `uv`-provisioned interpreter
instead; the operator may also keep the host interpreter, and the resolved interpreter SHALL be visible in
the preview for every instance.

#### Scenario: venv build is in the plan, not the render

- **WHEN** a workspace is generated with `18.0`
- **THEN** rendering the workspace files performs no venv build, and the applied plan runs
  `python3 -m venv .venv/odoo18` followed by `pip install -r <shared odoo-18.0>/requirements.txt`

#### Scenario: In-range host interpreter is used as-is

- **WHEN** a workspace is generated for a version whose declared Python range contains the host `python3`
- **THEN** the plan builds that instance's venv with the host `python3` and the preview names it, without a
  warning

#### Scenario: Out-of-range host interpreter is surfaced with a uv alternative

- **WHEN** a workspace is generated for a version whose declared Python maximum is below the host `python3`
  — for example an Odoo 14 instance on a host whose `python3` is 3.12
- **THEN** the flow reports the version's range, the detected host version and the bound's evidence tier, and
  offers to build that instance's venv with a matching `uv`-provisioned interpreter

#### Scenario: The generated helper script rebuilds with the same interpreter

- **WHEN** a workspace is generated where one version's venv is built with a `uv`-provided interpreter
- **THEN** the generated venv-setup script rebuilds that version's venv with that same interpreter, so
  re-running it cannot silently replace the venv with an out-of-range host interpreter

#### Scenario: The uv alternative is unavailable

- **WHEN** the operator asks for the `uv`-provisioned interpreter and `uv` is not present on the host
- **THEN** the flow says `uv` is required for that choice and points at the provisioning step, and no venv is
  built with an out-of-range interpreter unless the operator explicitly keeps the host one
