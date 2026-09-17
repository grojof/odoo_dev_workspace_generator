# Design

## Context

See `proposal.md` — Why. What shapes the approach is where the facts actually live, which the research for
this change established the hard way (2026-09-17):

- **The Odoo documentation states minima only.** No version's manual states a Python maximum, and the
  PostgreSQL floor is given as "supported versions: N.0 or above".
- **Its URL layout changes across eras**, and one page is a stub, so a naive "fetch the source-install page
  for each version" loop silently returns nothing for the old versions.
- **The maxima are in the repository, not the manual.** Each branch's `requirements.txt` splits its pins into
  buckets by `python_version`, and the comments name the target distribution (`(Jammy)`, `(Noble)`,
  `(Trixie)`, `(Resolute)`). The newest bucket is the newest interpreter that branch is maintained for. Odoo
  19 is the one version that also declares the bound outright — `MAX_PY_VERSION = (3, 14)` in
  `odoo/release.py` — and it **agrees** with the bucket derivation, which is what makes the derivation
  trustworthy for the versions that state nothing.
- The tool already has a working precedent for interpreter provisioning: F3's `uv`-native interpreters for
  migration steps, measured on this host. That is the mechanism to reuse, not a new one.

The layer contract from `CLAUDE.md` applies unchanged: the matrix is data in `models.py`, the planners stay
pure, and only `system.py` probes the host.

## Goals / Non-Goals

**Goals:**

- One data structure as the single source of every support bound, with the evidence tier inline so a caller
  cannot accidentally present a derived bound as an official requirement.
- A re-verification path that is a command, not a procedure a human follows: the research method encoded as
  a script plus the prose that explains its precedence rules and traps.
- Interpreter choice everywhere an environment is built, recommendation as default.

**Non-Goals:**

- Parsing `requirements.txt` at runtime. The derivation happens offline, in the verification script; the
  package only reads the declared matrix. Runtime parsing would make workspace generation depend on network
  and clone state for a fact that changes twice a year.
- Modelling per-dependency pins. The matrix bounds interpreters and PostgreSQL, not the pin sets — those
  stay where they are, in the migration overrides.
- A general OS-abstraction layer. Ubuntu 22.04/24.04 is a list, not a plugin point.

## Decisions

### D1: The matrix is a frozen dataclass per Odoo version, not parallel dicts

Today `ODOO_PYTHON_MINIMUM` and `MIGRATION_INTERPRETER` are separate dicts keyed by major, which is how a
version ends up with a cited floor and an uncited ceiling. Replace them with one `VersionSupport` frozen
dataclass (python min/max with tiers, recommended interpreter, acquisition method, PostgreSQL floor) in a
single `ODOO_SUPPORT` mapping, and keep the existing helper functions (`odoo_python_minimum`,
`migration_interpreter`) as thin readers over it so no caller breaks.

*Alternative considered:* keep the dicts and add a third for maxima. Rejected — it reproduces exactly the
fragmentation this change exists to remove.

### D2: Evidence tier is a value in the data, not a comment

Each bound is a `(value, tier, source)` triple rather than a bare string with a `#` comment above it, because
the requirement that output must not present a derived bound as official is only enforceable if the tier
travels with the value into `ui.py`. Three tiers: `official`, `derived`, `untested`.

*Alternative considered:* a module-level docstring listing sources (today's approach). Rejected — it cannot
reach the UI, which is where the honesty matters.

### D3: The ceiling for a version is the Python of the newest distribution its `requirements.txt` targets

Derivation rule, applied per branch: collect the `python_version` buckets, take the newest one, and read the
distribution named in its comment; the ceiling is that distribution's system Python. Cross-checked against
Odoo 19's own `MAX_PY_VERSION`, which this rule reproduces exactly.

*Alternative considered:* community reports (forum threads, issues). Rejected as the primary source after
reading them: the two most-cited threads for "Odoo 16 cannot run on Python 3.11" and "Odoo 17 fails on Python
3.12" are a macOS `psycopg2` linking error and an uninitialised database, neither of which is an interpreter
ceiling, and the repository data contradicts the conclusion both threads reach. They remain useful as
symptom references and are cited as such in the docs, never as bounds.

### D4: Interpreter resolution is a pure function; only probing touches the host

`resolve_interpreter(version, host_python, operator_choice) -> InterpreterChoice` lives with the planners as
pure logic and returns what to build with plus whether a warning is due. `system.py` supplies the host
`python3` version and which interpreters `uv` can provide. This keeps the new logic unit-testable with no
filesystem and no network, as `CLAUDE.md` requires of the test suite.

### D5: `provision check` reads the Ubuntu release, and keeps reporting rather than refusing

`check` stays read-only and non-judgemental: an unsupported release is a row, not an abort. Only `apply`
refuses. That preserves the existing split where `check` is safe to run anywhere — including on a host the
operator is evaluating.

### D6: The verification script lives outside the package

`tools/verify_support_matrix.py`, stdlib-only (`urllib.request`), never imported by `odoo_dwg`, not part of
the unit suite (it needs network). It re-derives each bound from its source and exits non-zero on drift, so
it can later become a scheduled CI job without touching the package. The "zero runtime dependencies" rule is
untouched: it is developer tooling, and it is the only thing in the repository allowed to reach the network.

### D7: The research procedure, recorded

This is the part the change exists to make repeatable. Sources in precedence order, per fact:

| Fact | Primary source | Secondary |
|---|---|---|
| Python minimum | `https://raw.githubusercontent.com/odoo/odoo/<v>/setup.py` → `python_requires` | the version's source-install page |
| Python maximum | `.../odoo/release.py` → `MAX_PY_VERSION` (19.0 only) | `.../requirements.txt` → newest `python_version` bucket + its distribution comment |
| PostgreSQL minimum | the version's source-install page → "supported versions: N.0 or above" | — |
| Host Python / PostgreSQL | `https://packages.ubuntu.com/<codename>/python3` and `/postgresql` | — |

Documentation URL layout, which is the main trap:

| Versions | Path |
|---|---|
| 12.0, 13.0 | `/documentation/<v>/setup/install.html` — **13.0 is a table-of-contents stub with no requirements text at all** |
| 14.0 | `/documentation/<v>/administration/install/source.html` |
| 15.0 – 19.0 | `/documentation/<v>/administration/on_premise/source.html` |

Traps worth writing down, all hit during this research:

1. Fetching a documentation page through a summarising fetcher returned *empty* content for every pre-17
   page while reporting success. Retrieve the HTML directly and strip the tags locally.
2. Sentence-splitting on `.` shreds "Python 3.10". Match `Python 3\.\d+` and
   `supported versions?: \d+\.\d+` as patterns instead.
3. Odoo 13's install page has no requirements text, so a documentation-only method has a silent hole exactly
   where it is least expected. The repository has no such hole — hence the precedence order above.
4. Codename → Python mapping must come from the distribution, not memory: Jammy 3.10, Noble 3.12,
   Resolute 3.14 (all read from `packages.ubuntu.com`), Trixie is Debian 13 (3.13).

### The matrix this produces

Host support: Ubuntu 22.04 (`python3` 3.10.6, PostgreSQL 14) and Ubuntu 24.04 (`python3` 3.12.3,
PostgreSQL 16, reference box). Tool floor: Python 3.10, being 22.04's system Python — matches the existing
`requires-python = ">=3.10"`.

| Odoo | Py min | tier | Py max | tier / basis | Recommended | PostgreSQL min |
|---|---|---|---|---|---|---|
| 12.0 | 3.5 | official (docs + `setup.py`) | — | untested (no bucket names a distribution) | Docker image | not stated |
| 13.0 | 3.6 | official (`setup.py`; docs page is a stub) | — | untested | Docker image | not stated |
| 14.0 | 3.7 | official docs — **`setup.py` says `>=3.6`** | 3.10 | derived (newest bucket: Jammy) | 3.8 | 12.0 |
| 15.0 | 3.7 | official (docs + `setup.py`) | 3.12 | derived (Noble) | 3.8 | 12.0 |
| 16.0 | 3.7 | official (docs + `setup.py`) | 3.13 | derived (Trixie) | 3.10 | 12.0 |
| 17.0 | 3.10 | official (docs + `setup.py`) | 3.14 | derived (Resolute) | 3.10 | 12.0 |
| 18.0 | 3.10 | official (docs + `setup.py`) | 3.14 | derived (Resolute) | 3.12 | 12.0 |
| 19.0 | 3.10 | official (`release.py` `MIN_PY_VERSION`) | 3.14 | **official** (`MAX_PY_VERSION`), agrees with Resolute | 3.12 | 13.0 |

Every `ODOO_PYTHON_MINIMUM` value the tool already carried is confirmed by this pass; what is new is the
maxima, the tiers, the Odoo 19 PostgreSQL floor and the Odoo 14 documentation/`setup.py` divergence. The
recommended column keeps F3's measured values for the migration path (which is why 15.0 recommends 3.8 even
though it tolerates 3.12) — the recommendation is "what this project has actually built and run", the range
is "what Odoo declares".

## Risks / Trade-offs

- **A derived ceiling is a maintenance claim, not a compatibility proof** → the tier says `derived`, the docs
  say what it is derived from, and the verification script re-derives it, so a branch that gains a Noble
  bucket next month shows up as drift rather than silently going stale.
- **Odoo 12/13 ceilings are `untested`** → they are only ever run through the Docker fallback today, so the
  unknown is inert. Whether they would run natively on `uv`'s floor of 3.8 (their buckets do reach
  `>= '3.8'`, without naming a distribution) is recorded as a validation item, not assumed either way.
- **Narrowing to Ubuntu breaks Debian hosts that `apply` used to accept** → deliberate and called out as
  BREAKING in the proposal; `check` still runs everywhere and reports, and `docs/provisioning.md` remains a
  reference for provisioning such a host by hand.
- **The verification script reaches the network and can rot** → it is developer tooling outside the package
  and outside the unit suite, so a 404 in it can never break the tool, only the check itself.
- **Recommending an interpreter the host cannot provide** (no `uv`) → the flow states the requirement and
  the operator keeps a working default; nothing is installed behind their back.
- **Two recommended-vs-range numbers per version can confuse** → the preview always prints both the chosen
  interpreter and the version's range, so the operator sees why a choice was offered.

## Migration Plan

The matrix replaces two dicts behind their existing accessors, so the change is internal until the new
surfaces are wired. Order: land the data + helpers with tests first (no behaviour change), then the
`provision check` rows, then the two interpreter-choice flows, then the docs and the verification script.
Rollback is per-step: the accessors keep their signatures, so reverting a later step leaves the matrix in
place and harmless.

## Open Questions

- Whether Odoo 12/13 can run natively on `uv`'s 3.8 floor instead of the Docker fallback. Deferrable: it
  would remove a dependency, not change any bound declared here, and it is answerable by the planned
  12 → 19 validation run (see `docs/roadmap.md`) rather than by more reading.
- Whether the 22.04 column needs a jammy container in CI to stay honest, or whether the
  `packages.ubuntu.com` citation suffices until the CI workflow lands. Does not affect the data or the specs.
