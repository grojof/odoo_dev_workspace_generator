# Tasks

## 1. The matrix as data

- [x] 1.1 Add `Evidence` (tier + source) and `VersionSupport` frozen dataclasses plus the `ODOO_SUPPORT`
      mapping for 12.0–19.0 in `models.py`, populated from the table in `design.md`; verify a new unit test
      asserts every version has a complete row and that the Odoo 19 Python maximum is tier `official`
- [x] 1.2 Add host facts to the matrix (supported Ubuntu releases with their system Python and PostgreSQL,
      plus the tool's own Python floor) and verify a unit test asserts the tool floor equals
      `requires-python` in `pyproject.toml`
- [x] 1.3 Reimplement `odoo_python_minimum` and `migration_interpreter` as readers over `ODOO_SUPPORT`,
      delete `ODOO_PYTHON_MINIMUM` and `MIGRATION_INTERPRETER`, and verify the existing `models` tests pass
      unchanged
- [x] 1.4 Add lookups for an unsupported version and for a Python-range check
      (`python_in_range(version, py) -> bool`), and verify unit tests cover below-min, in-range, above-max
      and unknown-version cases

## 2. Interpreter resolution

- [x] 2.1 Add the pure `resolve_interpreter(version, host_python, operator_choice)` returning the interpreter
      to build with, whether it is out of range, and the crossed bound's evidence tier; verify unit tests
      cover host-in-range, host-above-max, valid override and out-of-range override with no I/O
- [x] 2.2 Probe the host `python3` version and the interpreters `uv` can provide in `system.py`, and verify
      `provision check` renders them (manual run on this host, recorded in the task notes)
- [x] 2.3 Thread the resolved interpreter through `plan_build_venv` / `plan_generate_workspace` so the venv
      command uses it, keeping the planners pure; verify a unit test asserts the emitted command uses a
      `uv`-provisioned interpreter for an out-of-range case and plain `python3` for an in-range one
- [x] 2.4 Wire the workspace flow prompt (recommended default, operator may choose, `uv`-missing message) in
      `workflows/workspace.py`, and verify the preview names the interpreter per instance on a dry run

## 3. Migration per-step override

- [x] 3.1 Extend the migration environment model so each chain step carries a resolved interpreter with an
      optional operator override, and verify unit tests cover an overridden source step alongside
      recommended remaining steps
- [x] 3.2 Refuse an override for a Docker-fallback step (12/13) and verify a unit test asserts the refusal
- [x] 3.3 Wire the per-step prompt in `workflows/migration.py` and verify the generated per-step `odoo.conf`
      and `run_migration.sh` still pass `bash -n` with an overridden step

## 4. Host readiness

- [x] 4.1 Replace package-family detection with supported-release detection in `system.py` +
      `provisioning.py` (report, never abort), and verify unit tests cover a supported release, Debian, and
      an unknown OS
- [x] 4.2 Report the installed PostgreSQL server version against the matrix floor as its own row, and verify
      a unit test covers below-floor (WARN) and at-or-above (OK)
- [x] 4.3 Narrow the `provision apply` refusal to the declared releases in `workflows/provision.py`, and
      verify a unit test asserts it refuses before assembling any command
- [ ] 4.4 Run `provision check` on this Ubuntu 24.04 host and confirm the host row, the PostgreSQL version
      row and the `uv` interpreter row read correctly — **partially done**: the host row (Ubuntu 24.04 LTS
      (noble)), the `uv` row (provides 3.8–3.15) and the host-python3 row (3.12) all read correctly on
      this box. The PostgreSQL version row cannot be confirmed here: PostgreSQL is not installed and
      installing it needs `sudo` with a password. Unit-tested below/above the floor in the meantime

## 5. Re-verification tooling

- [x] 5.1 Write `tools/verify_support_matrix.py` (stdlib only, never imported by the package) that re-derives
      each bound per the precedence table in `design.md` — `setup.py`, `release.py`, `requirements.txt`
      buckets, the documentation pages, `packages.ubuntu.com` — and verify it exits zero against the matrix
      as landed
- [x] 5.2 Make the script report drift by version/fact/source and exit non-zero, and verify by temporarily
      perturbing one declared bound that it names exactly that bound
- [x] 5.3 Confirm the script is excluded from the unit suite and adds no runtime import, by verifying
      `python -m pytest -q` does not touch the network and `python -m odoo_dwg --help` still works

## 6. Docs and specs

- [x] 6.1 Write `docs/support-matrix.md`: the matrix with a source URL and verbatim quote per fact, the
      evidence tiers, the documentation-URL-layout table and the four retrieval traps, and the
      re-verification command; verify it renders the same numbers the code declares
- [x] 6.2 Point `README.md`, `docs/provisioning.md`, `docs/configuration-reference.md`, `docs/migration.md`
      and `docs/wsl-setup.md` at the matrix instead of restating bounds, and verify no stale "apt family" or
      per-version Python claim survives (`grep -rn "apt-family\|apt family\|Debian" README.md docs/`)
- [x] 6.3 Replace the placeholder `## Purpose` in all nine specs under `openspec/specs/`, and verify
      `openspec validate --specs` reports no warnings
- [x] 6.4 Update `CONTRIBUTING.md` with the re-verification command, and `CHANGELOG.md` `[Unreleased]`
- [x] 6.5 Update `docs/roadmap.md`: support matrix done, and record the validation items this change
      surfaced — a full 12 → 19 run against an Odoo 12 database built from Odoo's own demo data (which also
      answers whether 12/13 can run natively on `uv` 3.8 instead of Docker), and confirming the 22.04 column
      on a jammy host

## 7. Acceptance

- [x] 7.1 Run the four project checks green: `python -m pytest -q`, `python -m ruff check .`,
      `openspec validate --specs`, `python -m odoo_dwg --help`
- [x] 7.2 Generate a workspace profile containing both an in-range version (18.0) and an out-of-range one
      (14.0) on this host, and confirm the preview offers the `uv` interpreter only for 14.0 and that
      applying it builds both venvs
- [x] 7.3 Generate a migration environment with the source step overridden to a client-style interpreter and
      confirm the per-step interpreters in the preview and driver match the choice
