# workspace-generation Specification

## Purpose

Creates a workspace on disk from its profile: a shared read-only clone cache, the per-client tree, one virtual environment per Odoo version built with an interpreter that version supports, the per-version config and editor files, and a README that documents the result. Create-only and previewed, so it never clobbers work already there.

## Requirements
### Requirement: Shared read-only repo cache

The system SHALL maintain a shared repository cache under `<base>/.repos`, cloning each configured Odoo
version once with `git clone --branch <version> --single-branch` from `odoo/odoo`, and each configured OCA
repository once on the matching version branch. The cache SHALL be reused across workspaces, and generation
SHALL NOT re-clone a repository that is already present.

#### Scenario: Clone a version once

- **WHEN** generating a workspace whose version `18.0` is not yet in the cache
- **THEN** the plan includes `git clone --branch 18.0 --single-branch <odoo-url> <base>/.repos/odoo-18.0`

#### Scenario: Reuse an existing clone

- **WHEN** the shared cache already contains `odoo-18.0`
- **THEN** the plan contains no clone command for `18.0` and reuses the existing clone

### Requirement: Per-client workspace tree

The system SHALL generate, under `<base>/<name>/`, the directories `addons-custom/` and `addons-oca/` (the
latter holding symlinks into the shared OCA cache), a `config/odoo<major>.conf` per version, a `scripts/`
directory with `setup_venv.sh` and `run.sh` helpers, a `<name>.code-workspace` file, a `.vscode/` directory
(`tasks.json`, `launch.json`, `settings.json`, `extensions.json`), and a per-workspace `README.md`. All
generated files SHALL be English text.

#### Scenario: Full tree is planned

- **WHEN** a workspace `acme` with version `18.0` is generated
- **THEN** the plan creates `addons-custom/`, `addons-oca/`, `config/odoo18.conf`, `scripts/setup_venv.sh`,
  `scripts/run.sh`, `acme.code-workspace`, `.vscode/*`, and `README.md`

#### Scenario: Rendered odoo.conf carries the composed addons_path and derived port

- **WHEN** `config/odoo18.conf` is rendered for workspace `acme`
- **THEN** it contains an `addons_path` composed of custom + OCA + shared `odoo/addons` and the derived
  `http_port` for that version

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

### Requirement: Robust per-workspace README

The system SHALL write a per-workspace `README.md` that documents the workspace's Odoo versions, directory
layout, per-version ports and config paths, and the commands to set up the venv and run each instance, so that
any human or AI assistant has full context without any external tooling.

#### Scenario: README lists versions and run commands

- **WHEN** the per-workspace README is generated for a workspace with versions `17.0` and `18.0`
- **THEN** it lists both versions with their ports/config paths and the setup/run commands for each

### Requirement: Create-only generation is safe and previewed

Generation SHALL be create-only: it MUST NOT overwrite or delete an existing workspace's `addons-custom`
contents, venvs, or config. Every host-mutating step (clone, venv build, dependency install) SHALL be assembled
into a command plan, previewed, and applied only after confirmation.

#### Scenario: Existing workspace is not clobbered by generation

- **WHEN** generation targets a `<base>/<name>` that already exists
- **THEN** the operation refuses to overwrite existing custom addons/venvs/config and reports that management
  (not creation) is required

#### Scenario: Plan is previewed before any mutation

- **WHEN** the user starts a generation
- **THEN** the full command plan is displayed and no command runs until the user confirms
