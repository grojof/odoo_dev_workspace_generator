# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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

### Fixed
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
