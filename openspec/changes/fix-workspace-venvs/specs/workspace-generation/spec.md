## ADDED Requirements

### Requirement: Workspace venvs install the setuptools their Odoo version needs

Each per-instance venv SHALL install a `setuptools` release its Odoo version can run and build with:
`setuptools<58` for Odoo 13 and earlier (whose `vatnumber==1.2` still uses `use_2to3`), `setuptools<81` for
Odoo 14 to 16 (which import `pkg_resources` at startup), and an unpinned `setuptools` from Odoo 17. The
generated venv-setup script SHALL apply the same requirement as the generation plan.

#### Scenario: A pkg_resources-era workspace starts

- **WHEN** a workspace with `15.0` is generated on a host whose `python3` is 3.12
- **THEN** its venv installs `setuptools<81`, and `odoo-bin` starts without `ModuleNotFoundError: pkg_resources`

#### Scenario: A use_2to3-era workspace builds

- **WHEN** a workspace with `13.0` is generated
- **THEN** its venv installs `setuptools<58` before the requirements, and `vatnumber` builds

#### Scenario: Current versions are not pinned

- **WHEN** a workspace with `18.0` is generated
- **THEN** its venv installs an unpinned `setuptools`

## MODIFIED Requirements

### Requirement: Per-instance virtual environment

The system SHALL create one virtual environment per instance at `.venv/odoo<major>` and install that version's
dependencies from the cloned repo's `requirements.txt`. The venv creation and installation SHALL run only as
part of an applied plan, never during file generation.

The interpreter each venv is built with SHALL be resolved against the support matrix before the plan is
assembled. When the host `python3` is inside that version's declared Python range it SHALL be the default,
except that when the version states no Python maximum the host SHALL be the default only if it is no newer
than the matrix's recommended interpreter. When the host is not the default, the flow SHALL state why — the
range, the detected host version and the evidence tier of the bound being crossed, or that no maximum is
stated and the host is unproven — and offer to build that venv with a matching `uv`-provisioned interpreter
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

#### Scenario: An unstated maximum does not make a newer host the default

- **WHEN** a workspace is generated for Odoo 12 or 13, which state no Python maximum, on a host whose
  `python3` is 3.12
- **THEN** the default is the recommended `uv` interpreter (3.8), the flow says the host is unproven for that
  version rather than out of range, and the operator may still keep the host

#### Scenario: The generated helper script rebuilds with the same interpreter

- **WHEN** a workspace is generated where one version's venv is built with a `uv`-provided interpreter
- **THEN** the generated venv-setup script rebuilds that version's venv with that same interpreter, so
  re-running it cannot silently replace the venv with an out-of-range host interpreter

#### Scenario: The uv alternative is unavailable

- **WHEN** the operator asks for the `uv`-provisioned interpreter and `uv` is not present on the host
- **THEN** the flow says `uv` is required for that choice and points at the provisioning step, and no venv is
  built with an out-of-range interpreter unless the operator explicitly keeps the host one
