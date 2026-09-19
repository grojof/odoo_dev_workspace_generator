# workspace-generation Specification

## Purpose

Creates a workspace on disk from its profile: a shared read-only clone cache, the per-client tree, one virtual environment per Odoo version built with an interpreter that version supports, the per-version config and editor files, and a README that documents the result. Create-only and previewed, so it never clobbers work already there.

## Requirements

### Requirement: Shared read-only repo cache

The system SHALL maintain a shared repository cache under `<base>/.repos`, cloning each configured Odoo
version once with `git clone --depth 1 --branch <version> --single-branch` from `odoo/odoo`, and each
configured OCA repository once, the same way, on the matching version branch. The cache SHALL be reused across workspaces,
and generation SHALL NOT re-clone a repository that is already present.

The clone SHALL be shallow by default and without a profile option: a development workspace does not read the
branch history, which is most of a clone's size. The documentation SHALL state how to fetch the full history
(`git fetch --unshallow`) for whoever needs it, and refreshing the cache SHALL keep working on a shallow clone.

#### Scenario: Clone a version once

- **WHEN** generating a workspace whose version `18.0` is not yet in the cache
- **THEN** the plan includes `git clone --depth 1 --branch 18.0 --single-branch <odoo-url>
  <base>/.repos/odoo-18.0`

#### Scenario: OCA repositories are cloned the same way

- **WHEN** a workspace configures the OCA repository `web` for version `18.0`
- **THEN** the plan clones it with `--depth 1 --branch 18.0 --single-branch`

#### Scenario: Reuse an existing clone

- **WHEN** the shared cache already contains `odoo-18.0`, whether shallow or full
- **THEN** the plan contains no clone command for `18.0` and reuses the existing clone

#### Scenario: Refreshing a shallow clone

- **WHEN** the operator refreshes the shared repositories and a clone is shallow
- **THEN** the refresh advances it to the branch head the same way it does a full clone

### Requirement: Per-client workspace tree

The system SHALL generate, under `<base>/<name>/`:
- the directories `addons-custom/` and `addons-oca/`, the latter holding symlinks into the shared OCA cache;
- a `config/odoo<major>.conf` per version;
- a `scripts/` directory with `setup_venv.sh` and one `run-odoo<major>.sh` per version;
- a `<name>.code-workspace` file;
- a `.vscode/` directory (`tasks.json`, `launch.json`, `settings.json`, `extensions.json`);
- an `odools.toml` when at least one version is supported by the language server;
- a per-workspace `README.md`;
- a `workspace.json` holding the resolved profile, so the workspace can be managed later.

All generated files SHALL be English text and SHALL hold exactly the rendered content.

#### Scenario: Full tree is planned

- **WHEN** a workspace `acme` with version `18.0` is generated
- **THEN** the plan creates `addons-custom/`, `addons-oca/`, `config/odoo18.conf`, `scripts/setup_venv.sh`,
  `scripts/run-odoo18.sh`, `acme.code-workspace`, `.vscode/*`, `odools.toml`, `README.md` and
  `workspace.json`

#### Scenario: Rendered odoo.conf carries the composed addons_path and derived port

- **WHEN** `config/odoo18.conf` is rendered for workspace `acme`
- **THEN** it contains an `addons_path` composed of custom + OCA + shared `odoo/addons` and the derived
  `http_port` for that version

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

### Requirement: Editor configuration for the official Odoo language server

The system SHALL write an `odools.toml` at the workspace root holding one `[[config]]` profile per Odoo
version in the workspace that the language server supports (14 and above; it refuses older versions). A
workspace with no supported version SHALL get no `odools.toml`. Each profile SHALL set only `name`, `odoo_path`, `addons_paths` and
`python_path`, as absolute paths: `odoo_path` pointing at that version's clone in the shared cache,
`addons_paths` at the workspace's own custom and OCA add-on directories for that version, and `python_path`
at that version's virtualenv interpreter. The file SHALL NOT use template variables, profile inheritance or
options the language server documents as version-specific, so that it stays valid across its releases.

The workspace SHALL recommend the official `Odoo.odoo` extension, and SHALL NOT recommend a third-party Odoo
extension in its place. The workspace settings SHALL turn the Python extension's own language server off, so
that Python sources are analysed by one server only.

The system SHALL NOT generate a `jsconfig.json`: JavaScript and OWL support comes from the language server
itself, reading the manifests' asset bundles.

#### Scenario: One profile per version with the documented minimal keys

- **WHEN** a workspace `acme` with versions `17.0` and `18.0` is generated
- **THEN** its `odools.toml` holds two `[[config]]` profiles, each setting exactly `name`, `odoo_path`,
  `addons_paths` and `python_path`, with `odoo_path` at that version's shared clone and `python_path` at
  `.venv/odoo<major>/bin/python`

#### Scenario: Versions the language server refuses get no profile

- **WHEN** a workspace holds versions `13.0` and `18.0`
- **THEN** its `odools.toml` holds a profile for 18.0 only and names 13.0 as skipped in a comment, and a
  workspace holding only `12.0` gets no `odools.toml`

#### Scenario: Paths are absolute and free of template variables

- **WHEN** the `odools.toml` of any workspace is rendered
- **THEN** every path is absolute and no `${...}` or `$...` template token appears in it

#### Scenario: Core add-ons come from the Odoo path, not the add-on list

- **WHEN** the profile for version `18.0` is rendered
- **THEN** its `addons_paths` lists the workspace's custom and OCA directories for 18.0 and does not repeat
  the clone's own `addons` directory, which the language server loads from `odoo_path`

#### Scenario: The official extension is recommended

- **WHEN** `.vscode/extensions.json` is rendered
- **THEN** it recommends `Odoo.odoo` and does not recommend `trinhanhngoc.vscode-odoo`

#### Scenario: One Python analyser, not two

- **WHEN** `.vscode/settings.json` is rendered
- **THEN** it sets `python.languageServer` to `None`

#### Scenario: No jsconfig is generated

- **WHEN** a workspace is generated
- **THEN** the plan writes no `jsconfig.json`

### Requirement: The language-server configuration is re-verifiable against its published schema

The project SHALL record which language-server release its emitted configuration was last reviewed against,
and SHALL provide a check that downloads the configuration schema published with the latest stable release,
verifies that every key and value type the generator emits is still accepted, lists the schema's keys the
generator does not use, and reports the release notes published since the recorded review. The check SHALL
exit non-zero when an emitted key is no longer accepted or its type changed, SHALL never modify the
generator, and SHALL NOT be imported by the package at runtime. The procedure for acting on its findings
SHALL be documented.

#### Scenario: A removed or retyped key fails the check

- **WHEN** the latest stable schema no longer accepts a key the generator emits, or accepts it with an
  incompatible type
- **THEN** the check names the key, the schema's release and the conflict, and exits non-zero

#### Scenario: New features are surfaced, not adopted

- **WHEN** the latest stable schema accepts keys the generator does not emit
- **THEN** the check lists them for review and still exits zero, leaving the generator unchanged

#### Scenario: Releases since the last review are shown

- **WHEN** the latest stable release is newer than the one the configuration was last reviewed against
- **THEN** the check prints the changelog entries in between, so the reviewer reads what changed

### Requirement: Workspace venvs install the build tooling their Odoo version needs

Each per-instance venv SHALL install a `setuptools` release its Odoo version can run and build with:
`setuptools<58` for Odoo 13 and earlier (whose `vatnumber==1.2` still uses `use_2to3`), `setuptools<81` for
Odoo 14 to 16 (which import `pkg_resources` at startup), and an unpinned `setuptools` from Odoo 17. Where a
branch pins a deprecated project that no longer builds, the venv SHALL install its declared successor instead:
for Odoo 12, `python-ldap==3.1.0` in place of `pyldap`. The generated venv-setup script SHALL apply the same
requirements as the generation plan.

#### Scenario: A pkg_resources-era workspace starts

- **WHEN** a workspace with `15.0` is generated on a host whose `python3` is 3.12
- **THEN** its venv installs `setuptools<81`, and `odoo-bin` starts without `ModuleNotFoundError: pkg_resources`

#### Scenario: A use_2to3-era workspace builds

- **WHEN** a workspace with `13.0` is generated
- **THEN** its venv installs `setuptools<58` before the requirements, and `vatnumber` builds

#### Scenario: Odoo 12 replaces the deprecated pyldap

- **WHEN** a workspace with `12.0` is generated
- **THEN** its venv installs the branch's requirements without `pyldap` plus `python-ldap==3.1.0`, in the plan
  and in the generated venv-setup script alike, and the shared clone is not modified

#### Scenario: Current versions are not pinned

- **WHEN** a workspace with `18.0` is generated
- **THEN** its venv installs an unpinned `setuptools`

### Requirement: Debug launch configurations for everyday development

The generated `.vscode/launch.json` SHALL contain four debugpy configurations for each configured version.
All of them SHALL use that version's venv interpreter and `odoo-bin`, run in the integrated terminal and set
`justMyCode` off:
- **server:** `-c config/odoo<major>.conf`;
- **shell:** `shell -c config/odoo<major>.conf -d <database>`, Odoo's interactive shell;
- **upgrade modules:** `-c config/odoo<major>.conf -d <database> -u <modules>`, which keeps serving after the
  upgrade;
- **test module:** `-c config/odoo<major>.conf -d <database> -u <module> --test-enable --test-tags /<module>
  --stop-after-init`.

The database, the modules and the test module SHALL be asked when a configuration starts, through
`launch.json` inputs. The database input SHALL default to the workspace name.

#### Scenario: Four configurations per version

- **WHEN** a workspace `acme` with versions `17.0` and `18.0` is generated
- **THEN** `launch.json` has eight configurations: server, shell, upgrade modules and test module for each
  version

#### Scenario: The shell asks for its database

- **WHEN** the Odoo 18 shell configuration is started
- **THEN** it prompts for the database, offering `acme`, and runs
  `odoo-bin shell -c <workspace>/config/odoo18.conf -d <answer>`

#### Scenario: Testing one module

- **WHEN** the Odoo 18 test module configuration is started and `sale` is entered as the module
- **THEN** it upgrades `sale`, runs only the tests tagged `/sale` and stops

### Requirement: Development posture in the generated odoo.conf

Each generated workspace `odoo.conf` SHALL be a development configuration:
- `http_interface = 127.0.0.1`, so an instance is reachable from the host only;
- `workers = 0` and `max_cron_threads = 1`, so Odoo runs threaded and a debugger can attach;
- `dev_mode = qweb,xml`, and never `reload`: reload re-executes the process on a file change, which detaches
  the debugger every generated launch configuration attaches;
- `admin_passwd = admin`, Odoo's database-manager password — a development default, documented as such.

#### Scenario: The debugger is never detached by a reload

- **WHEN** `config/odoo18.conf` is rendered
- **THEN** its `dev_mode` is `qweb,xml` and contains no `reload`, so installing `watchdog` cannot start
  re-executing the process

#### Scenario: Instances listen on loopback only

- **WHEN** any version's config is rendered
- **THEN** it sets `http_interface = 127.0.0.1`, `workers = 0` and `max_cron_threads = 1`

### Requirement: Workspace mail goes to the local capture

Each generated workspace `odoo.conf` SHALL set `smtp_server = 127.0.0.1` and `smtp_port = 1025`, so that mail
sent through the configuration server reaches the local capture when it runs and is refused when it does
not. It is never delivered elsewhere.

#### Scenario: SMTP keys in odoo.conf

- **WHEN** `config/odoo18.conf` is rendered
- **THEN** it contains `smtp_server = 127.0.0.1` and `smtp_port = 1025`
