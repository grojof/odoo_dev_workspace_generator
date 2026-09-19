# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Outbound firewall and mail capture** (change `add-egress-control`), both opt-in in `provision apply`, see
  [`docs/egress-control.md`](docs/egress-control.md).
  - **OpenSnitch 1.8.0** is installed from the upstream release, with SHA-512 pinned from the maintainer-signed
    list.
  - **Hardened configuration:** deny by default whether or not its window is open, `proc` process monitoring
    (`ebpf` lost long-running processes on WSL), rules applied to connections without a visible process
    (WSL's localhost relay, so the Mailpit UI opens from Windows), no connection flush on start, and fail
    closed.
  - **Baseline `00-odwg-*` rules** that come before any other rule:
    - localhost, DNS, NTP and the VS Code server;
    - **Odoo (`odoo-bin`) confined to localhost**;
    - GitHub, PyPI, `uv`, the Ubuntu archives and npm for the development tools.
  - **Mailpit 1.31.2** runs as a loopback-only service. Workspace and migration `odoo.conf` send mail to it.
  - **Redirect a database's mail to Mailpit** retargets a rehearsal copy's own mail servers and stops fetchmail,
    on Odoo 12–19.
  - **Every firewall decision reaches the system journal** (`journalctl -t opensnitch`), with or without its
    window.
  - **A `provision` submenu** turns each component off or on, persistently across restarts, or uninstalls it.
    For OpenSnitch it shows what `apt` will remove first and keeps your own rules.
  - `provision check` reports both and flags a softened firewall configuration.
  - `tools/verify_egress_pins.py` re-checks the pins, the signature and the signing key against upstream.

### Changed
- **Profiles are validated whenever they are loaded**, including when a workspace is managed. Versions must be
  exactly one of `12.0` … `19.0`; OCA repository names, `db_host`, ports and Python versions are checked too.
  **BREAKING** only for profiles that relied on looser values such as `"18"`.
- The unused `addon_prefix` profile field is gone. Old profiles that carry it still load, and it is ignored.
- `provision check` and the migration preflight **never ask for a password**. PostgreSQL's state and version
  come from `pg_lsclusters`; the development role is checked by logging in as it, or through `sudo -n`. When
  neither works, the role row says it could not be checked (WARN) instead of MISSING.
- **Refresh generated files** keeps a dated backup (`<file>.bak-<date>`), so a later refresh never overwrites
  an earlier one.
- The outbound firewall's development-infrastructure rule also allows the Ubuntu archive's country mirrors
  (`es.archive.ubuntu.com`, …).

### Fixed
- **Shell injection through versions and profiles.** A migration source or target such as `13.0$(…)`, or a
  version, name, `db_host` or OCA repository in a `workspace.json`, passed validation and reached generated
  scripts (`run_migration.sh`, `setup_venv.sh`, `run-odoo*.sh`) or `odoo.conf`. All of them are now validated.
  Generated scripts quote every path with `shlex.quote`.
- **The migration driver did not resume from the last good step.** It skipped completed steps, but re-ran a
  failed one on the half-migrated working database. It now restores the newest checkpoint first. It also
  binds the run to its source dump by SHA-256, and refuses a different dump instead of ignoring it.
- **Coverage for the ≤ 13 steps looked in the wrong places**, in the preflight and in the driver. That made
  every core module look "dropped by Odoo", and renames were read from the ≥ 14 location. Both now read the
  fork's own `addons`, `odoo/addons` and `openupgrade_records/lib/apriori.py`.
- **Pinning another Python for an already-built migration step had no effect.** The venv was kept because of
  its ready marker. It is now rebuilt when its `pyvenv.cfg` names another interpreter.
- **Add a version** added the version to the loaded profile even when its plan was declined or failed.
- **Invalid input crashed the CLI with a traceback:** a version like `3.x`, a malformed `workspace.json`, or a
  port given as text. It is now reported, and the CLI returns to the menu.
- **An interrupted OpenSnitch install could leave `/usr/sbin/policy-rc.d` behind,** which stopped every
  service from starting after later `apt` installs. It is removed on any exit, and a leftover of the tool's
  own is recognised.
- **Smaller fixes:**
  - the OpenSnitch configuration is written atomically;
  - a missing `apriori.py` is no longer cached for the whole session;
  - `provision apply` says when no verified wkhtmltopdf is pinned for the host;
  - staging no longer hides `git` failures;
  - the Python 3.10 gevent repair matches any 3.10 patch level.
- **The rtlcss option (right-to-left languages) installed 455 packages.** `apt` added every recommended package, a GUI terminal among
  them. It now installs `nodejs` and `npm` without recommends, and the prompt says what the step is for:
  only right-to-left languages (Arabic, Hebrew, Persian…).

## [0.1.0] - 2026-09-19

First release.

### Added
- **Manage → Refresh generated files** (change `refresh-generated-files`) brings an existing workspace's
  generated files up to date with the tool.
  - It writes only the files whose content changed, and keeps each previous version as `<file>.bak`.
  - It reads each venv's interpreter from its `pyvenv.cfg`.
  - It never touches addons, venvs, clones or databases.
- The Spanish UI is complete, and a test now fails if an operator-facing string has no Spanish entry.
- **Debug configurations for the shell, module upgrades and tests** (change `add-odoo-shell-launch`). Each
  version's `launch.json` now has four debugpy configurations:
  - the server;
  - `odoo-bin shell` with `env` bound to a database;
  - the server upgrading modules on start (`-u`);
  - one module's tests (`--test-enable --test-tags /<module> --stop-after-init`).

  VS Code asks for the database and modules when a configuration starts. The generated README lists them, and
  `tools/verify_workspace_versions.py` now runs them from the generated file on every version.
- **Official Odoo extension support** (change `use-official-odoo-language-server`). Generated workspaces carry
  an `odools.toml` for the official language server (OdooLS): one profile per Odoo version ≥ 14 (OdooLS
  refuses older ones), using only the four documented minimal keys — `name`, `odoo_path`, `addons_paths`,
  `python_path` — as absolute paths, so the file stays valid across releases of a strict schema. Pick the
  profile from the status bar. New `tools/verify_odools_config.py` checks the emitted keys against the latest
  stable release's published schema, lists keys not yet emitted, and prints the release notes since the
  release last reviewed; [`docs/editor-integration.md`](docs/editor-integration.md) documents the update
  procedure.
- **Support matrix** (change `add-support-matrix`): one authoritative, evidence-tiered declaration of what
  the tool supports — host releases, the tool's own Python floor, and per-Odoo-version Python range,
  recommended interpreter and PostgreSQL floor — in `models.py` (`ODOO_SUPPORT`/`SUPPORTED_HOSTS`), which
  `provision check`, workspace generation and migration all read instead of restating. Each bound carries
  its evidence tier (`official` / `derived` / `untested`) and source, so output never presents a derived
  bound as an Odoo requirement. New `docs/support-matrix.md` cites every fact verbatim and records the
  retrieval procedure; new `tools/verify_support_matrix.py` (stdlib-only, outside the package and the test
  suite) re-derives every bound from its official source and exits non-zero on drift.
- **Per-version Python maxima**, which the tool did not model before, derived from the newest interpreter
  bucket each Odoo branch declares in its own `requirements.txt` and the distribution its comment names
  (Jammy/Noble/Trixie/Resolute) — a derivation that reproduces Odoo 19's declared `MAX_PY_VERSION = (3, 14)`
  exactly. Odoo 12/13 declare no ceiling and are marked `untested` rather than assumed.
- **Interpreter selection when building environments.** Workspace generation builds each venv with the host
  `python3` while it is inside that version's range, and otherwise reports the range, the detected version
  and the crossed bound's tier and offers a matching `uv`-provisioned interpreter (`uv venv --seed`, so the
  venv still has `pip`). Migration environments take each step's interpreter from the matrix recommendation
  and let the operator **pin any step** to a specific Python — the way to rehearse on a client's own
  interpreter — with the step's requirements repair following the interpreter actually in use. Every step
  can be pinned, 13 included, since no step runs in a container any more.
- `provision check` now reports the host release against the supported list, the installed PostgreSQL server
  version against the floor of the versions in play, the host `python3`, and which interpreters `uv` can
  provide.

- **`tools/verify_workspace_versions.py`**: builds a throwaway workspace with every supported Odoo version
  through the tool's own plan, installs `base` and serves `/web/login` on each, then removes what it created.
  It is the documented procedure for re-checking that every version still builds and starts
  ([`docs/workspace-layout.md`](docs/workspace-layout.md#re-verifying-every-version)).
- **The generated README states what each venv installs**: its Python (host or `uv`), its setuptools rule
  and any requirement replaced, with the reason, so anyone reading the workspace, human or assistant, knows
  exactly what runs. `docs/workspace-layout.md` carries the same table for every version, as last verified.

### Changed
- Workspaces recommend the **official** `Odoo.odoo` extension instead of the third-party
  `trinhanhngoc.vscode-odoo`, and set `python.languageServer` to `None` so Pylance does not analyse Python
  alongside OdooLS. No `jsconfig.json` is generated: OdooLS 1.5 resolves JavaScript and OWL itself.
- **BREAKING — Docker is no longer used or required** (change `drop-docker-run-13-natively`). The Odoo 13
  step, the only step that ever ran in a container, now runs natively in a `uv` virtualenv on Python 3.8
  like every other step. `provision check` drops the Docker rows, `provision apply` drops the Docker Engine
  install and the `odoo:13.0`/`odoo:12.0` image pulls, and the migration preflight and driver stop requiring
  a daemon. A host that installed Docker for earlier versions can keep or remove it freely.

- **BREAKING — Ubuntu 24.04 is the only supported host**, narrowed from the whole Debian/Ubuntu apt family
  (changes `add-support-matrix`, then `lighten-scope`). `provision check` reports any other host as
  unsupported (it still completes and still changes nothing) and `provision apply` refuses before assembling a
  single command. Debian and Ubuntu 22.04 had been declared but never run on a real host, so the claim was
  dropped rather than left implied.
- **BREAKING — the tool needs Python 3.12** (24.04's system Python; `requires-python = ">=3.12"`), up from
  3.10, which existed only to honour 22.04.
- **Workspace clones are shallow** (`--depth 1`, Odoo and OCA alike), with no option to configure. A full
  single-branch Odoo clone measured 4.2–5.7 GB, almost all history; a shallow one is about 1 GB. Existing clones
  are left untouched, **Refresh shared repos** keeps working, and `git fetch --unshallow` restores history for
  whoever needs `log`/`blame`.
- **Workspaces connect as the shared `odoo` role by default** (change `default-shared-db-role`), the role
  `provision apply` creates by default and migration environments use. `db_user` used to default to the
  workspace name, a role nobody had created, so a freshly provisioned host could not serve a new workspace.
  Existing workspaces keep their role (it is recorded in `workspace.json`); a profile can still set
  `db_user`. Odoo's database selector now lists every development database on the host.

### Fixed
- **Add a version** rewrote every generated file without the interpreters, so `setup_venv.sh` and the README
  of a workspace with a `uv` venv claimed the host `python3`. It also overwrote hand edits. It now keeps each
  venv's interpreter and backs up what it changes.
- Generated files carried an extra blank line at the end. They now hold exactly the rendered content.
- **PostgreSQL role names are validated.** The role typed into `provision apply` was interpolated unquoted
  into SQL run as `postgres`, and a profile's `db_user` was written through a shell heredoc; both now must
  be a plain PostgreSQL identifier (`^[a-z_][a-z0-9_]{0,62}$`) and are rejected before any plan is built.
- **Workspace venvs for Odoo ≤ 16 failed to start, and Odoo ≤ 13 venvs failed to build** (change
  `fix-workspace-venvs`). The venv step installed the latest setuptools: on Python 3.12 that is 81+, which
  no longer ships the `pkg_resources` Odoo ≤ 16 imports at startup (`ModuleNotFoundError` on F5 in an Odoo 15
  workspace), and for Odoo ≤ 13 `vatnumber==1.2` cannot build with setuptools ≥ 58 (`use_2to3 is invalid`).
  Workspace venvs now install `setuptools<58` (≤ 13), `setuptools<81` (14–16) or an unpinned one (≥ 17), in the
  plan and in `setup_venv.sh` alike. The migration already pinned it and is unchanged. Odoo 12/13 workspaces
  also defaulted to the host's Python 3.12 — their maximum is unstated, and an unstated maximum bounded
  nothing — where their pinned `gevent` does not build; they now default to the recommended `uv` 3.8, and
  the prompt says the host is unproven rather than out of range. And Odoo 12 venvs install `python-ldap==3.1.0`
  in place of the deprecated `pyldap==2.4.28`, which does not build on `uv`'s Python 3.8.
- **Generated files can no longer break out of their heredoc.** Every file is written with a quoted
  heredoc whose delimiter was a fixed `EOF`, so a profile value carrying a newline and a line `EOF` (a
  hand-edited `db_host`, `addon_prefix` or OCA repo name) ended the heredoc early and ran the rest as shell
  commands — reproduced before the fix. The delimiter is now chosen so that no content line equals it.
- **The containerised Odoo 13 step silently under-migrated.** The `odoo:13.0` image sets
  `addons_path = /mnt/extra-addons`, so the mounted OpenUpgrade fork's `odoo-bin` loaded the *image's*
  add-ons; in the ≤ 13 layout every migration script lives inside its add-on, so only core scripts ran and
  the step still reported success. Measured against the same database: the container left
  `iap_account.company_id` untouched and the orphan column survived to Odoo 19, where the model declares
  `company_ids`; with IAP accounts present, the post-migration that moves the data would never run. The
  native step names the fork's `addons` directory explicitly and applies those scripts. Verified on WSL:
  a full 12 → 19 chain now ends with `openupgrade_legacy_13_0_company_id` and the `company_ids` relation,
  and no orphan column.
- The Odoo 13 requirements need `setuptools<58` as a **build** constraint (`vatnumber==1.2` still calls
  `use_2to3`). Build constraints are generated per version as `requirements/constraints-<ver>.txt` and
  applied with `uv pip install --build-constraints`, separate from the existing requirement overrides.
- **A real 12 → 19 migration could not run at all** (change `fix-preflight-coverage-classification`), which
  the first end-to-end run against an Odoo 12 database built from Odoo's own demo data exposed:
  - The per-step addons coverage check treated every installed module as the operator's code, so core
    modules Odoo renamed (`web_editor` → `html_editor`), merged (`web_kanban_gauge` → `web`) or deleted
    (`web_settings_dashboard`, `web_diagram`) each aborted the driver with "place it in
    `addons/odoo<major>/custom`". They are `auto_install` dependencies of `base`, so every Odoo 12 database
    hit it. Coverage now resolves the renames and merges OpenUpgrade declares in its own `apriori.py`, and
    classifies what is left by author: Odoo's own dropped code warns, anyone else's blocks. The driver
    refuses only on the blocking class.
  - Steps running Odoo ≤ 16 died at import with `ModuleNotFoundError: No module named 'pkg_resources'`.
    Nothing declares `setuptools`, so it arrived transitively and its version followed the step's
    interpreter — the 3.8 steps resolved 75.x and worked, the 3.10 steps resolved 84.x and failed.
    Those venvs now pin `setuptools<81`.
  - Accepted on WSL Ubuntu 24.04: 12 → 19 completed with eight checkpoints and the database at
    `base 19.0.1.3`, data intact, `html_editor` installed and the dropped modules gone.
- Odoo 19's PostgreSQL floor was carried as 12; it is 13 ("Changed in version 19: Minimum requirement
  updated from PostgreSQL 12 to PostgreSQL 13").
- The Odoo 15/16 Python floor (3.7) was an uncited assumption and is now anchored to both the documentation
  and `setup.py`. Odoo 14's documentation/`setup.py` divergence (3.7 vs `>=3.6`) is recorded rather than
  silently resolved.
- All nine capability specs carried the placeholder `## Purpose` that `openspec archive` writes, which
  `openspec validate --specs` warned about on every run; each now states what its capability is for.
- F0 foundation: package skeleton `odoo_dwg/` (i18n, ui, prompts, system, models, cli, workflow stubs),
  root entry point, interactive menu and argparse CLI (`workspace`/`provision`/`migrate`).
- English-canonical UI with an optional Spanish catalog (`ODWG_LANG=en|es`).
- Domain model: `WorkspaceConfig`/`InstanceConfig`, official Python-floor facts, deterministic per-version
  ports, JSON round-trip.
- Project conventions: `CLAUDE.md`, OpenSpec initialized (`openspec/`, `.claude/`), `docs/roadmap.md`,
  robust `README.md`, `pyproject.toml` (ruff + pytest, zero runtime dependencies).
- Unit tests for `models` and `i18n`.
- **F1 workspace section**: JSON-profile-driven generation of a per-client workspace — shared repo cache
  (`git clone --branch <ver> --single-branch`), per-version `odoo.conf`, per-instance venv, `addons-custom`/
  per-version `addons-oca` symlinks, VSCode files, `scripts/`, and a robust per-workspace README. Pure
  `templates.py` + `planners.py` (`plan_repo_cache`/`plan_workspace_tree`/`plan_build_venv`/
  `plan_generate_workspace`/`plan_refresh_repos`); create-only vs manage-only flows in `workflows/workspace.py`
  over plan → preview → apply. Example profile in `examples/`. Docs: `docs/workspace-layout.md`,
  `docs/configuration-reference.md`.
- **F2 provision section**: host-agnostic (Debian/Ubuntu apt) system provisioning. `provision check` renders a
  read-only host-readiness table; `provision apply` (root-gated, previewed, idempotent) installs the Odoo
  build dependencies, PostgreSQL + a dev role (with loopback trust for development), the checksum-verified
  patched wkhtmltopdf (0.12.6 for Odoo ≥ 15), and optional Node + rtlcss. New `provisioning.py` (facts + pure
  `provision_rows`), provision planners in `planners.py`, host probes in `system.py`, wired in
  `workflows/provision.py`. Docs: `docs/provisioning.md`. Validated end-to-end on WSL Ubuntu 24.04.
- **F3 migration mode**: generates an OpenUpgrade migration environment for a source → target chain
  (sequential, no skips). Data-backed interpreter strategy (measured on WSL): `uv` native interpreters for
  Odoo ≥ 14 (14/15→3.8, 16/17→3.10, 18/19→3.12) and a Docker fallback (`odoo:13.0`/`odoo:12.0`) for the
  Python-3.6/3.5 steps. `MigrationEnv` + `migration_chain`/`migration_interpreter` in `models.py`; migration
  planners (`plan_migration_clones`/`plan_migration_venvs`/`plan_migration_configs`/`plan_generate_migration`)
  and templates (per-step `odoo.conf`, checkpointing `run_migration.sh`, Docker recipe); wired in
  `workflows/migration.py`. Docs: `docs/migration.md`.

- Migration menu: **Clean a migration environment** — removes a `<src>-to-<tgt>` environment directory
  (venvs, configs, checkpoints, logs, requirements, driver) over plan → preview → apply with an
  exact-phrase confirmation (`DELETE`); optionally also the shared `.repos` clone cache (opt-in, it
  serves every environment). The PostgreSQL migration database is deliberately untouched.

- **Migration preflight & Docker readiness** (change `add-migration-preflight`): `provision check` now
  reports `uv` and Docker (binary / daemon / OpenUpgrade fallback images as distinct signals) and
  `provision apply` gains opt-in plans for Docker Engine (`docker.io`) and `docker pull odoo:13.0`/`12.0`.
  New migration-menu **Preflight check** (chain-scoped host checks — Docker rows only when the chain has a
  12/13 step —, PostgreSQL/role, dump integrity via `pg_restore --list`, and against a named database:
  actual source version from `ir_module_module`, installed modules, per-step addons coverage naming the
  exact directory to fill, and a per-custom-module adaptation warning). The generate flow shows the host
  preflight first (MISSING requires explicit confirmation) and `run_migration.sh` embeds the same checks:
  host before restore, database right after the initial restore and before step 1, aborting non-zero with
  the failed check named. Migration environments now define `addons/odoo<major>/{custom,oca}` per version,
  threaded into each step's `addons_path` ahead of OpenUpgrade and core.

- **Custom-module staging** (change `add-custom-module-staging`): migration menu action **Stage custom
  modules** — per chain step it copies the previous stage's code into `addons/odoo<major>/custom` and runs
  OCA `odoo-module-migrator` for exactly that bump (tool installed into a shared uv venv via a previewed
  plan; the operator's source is never modified), cross-references the staged code against the step's
  OpenUpgrade `upgrade_analysis.txt` files (removed core fields/models → candidate findings with
  file:line; generic names excluded), writes inert `pre-migration.py` scaffolds (never overwriting —
  `pre-migration.generated.py` beside existing files), and produces `staging/report-<module>.md` with the
  tool log verbatim. Staging is a prepared starting point; developer review completes the migration.

- New `docs/wsl-setup.md`: a step-by-step guide to set up an Ubuntu 24.04 host on WSL 2 for the tool
  (install, user creation, systemd check, optional custom instance name, cloning into the Linux file
  system, `provision` check/apply, optional `uv`/Docker and editor setup). Anchored to Microsoft Learn;
  linked from the README. The tool still never creates a host — the environment stays the user's.

- Docs refreshed to the eunomai living-docs v2 standard with the **CLI-tool profile**: new
  `docs/commands.md` (full command/menu/phrase reference), README reshaped as a product map (Mermaid
  plan→preview→apply flowchart, real invocations, surface-organized index), new `SECURITY.md` (private
  reporting via GitHub Security Advisories) and `CONTRIBUTING.md`; `docs-check` green.
- Migration step configs now put the OpenUpgrade checkout **root** on `addons_path` (previously the
  `openupgrade_scripts` module directory itself), so `openupgrade_framework` resolves as the official
  OpenUpgrade run instructions require.
- Migration environment generation failed at the first requirements-overrides write
  (`cat > .../requirements/overrides-<ver>.txt`: "No such file or directory"): the `mkdir -p` for
  `requirements/` ran only in the configs planner, *after* the venvs planner that writes the overrides.
  `plan_migration_venvs` now creates the directory itself before its first write (found running a real
  12 → 18 generation on WSL).
- Migration venvs are now created with `uv venv --no-project`: without it, uv discovers any
  `pyproject.toml` at the caller's working directory (e.g. this repo's own, `requires-python >=3.10`)
  and emits a spurious incompatibility warning when building the 3.8 venvs for Odoo 14/15.
- The migration `requirements/overrides-<ver>.txt` was written but never applied; the requirements
  install now passes it via `uv pip install --overrides`. Its content is no longer a placeholder:
  for the Python-3.10 steps (Odoo 16/17, whose branches pin `gevent==21.8.0` — no cp310 wheel and an
  sdist that no longer compiles under modern Cython) it lifts to the branches' own 3.11 pins,
  `gevent==22.10.2` + `greenlet==2.0.2`. Validated with a real install on WSL.
- Interrupted venv builds now resume correctly: each finished venv is stamped with a `.odwg-ready`
  marker and the venvs planner skips on the marker (not the venv directory), rebuilding half-built
  venvs with `uv venv --clear` instead of silently skipping them.

[Unreleased]: https://github.com/grojof/odoo_dev_workspace_generator/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/grojof/odoo_dev_workspace_generator/releases/tag/v0.1.0
