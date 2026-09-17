# Proposal

## Why

The tool states its support boundaries in several places at once — `ODOO_PYTHON_MINIMUM` and
`MIGRATION_INTERPRETER` in `models.py`, the `provision check` rows, `requires-python` in `pyproject.toml`,
and prose across `README.md` and `docs/` — with no single authority and no citations. Some statements are
uncited (the Odoo 15/16 Python floors), one is stale (Odoo 19 raised its PostgreSQL floor to 13), and the
tool models no Python *maximum* at all, so a dev workspace builds every venv from the host `python3` and an
Odoo 14 workspace on Ubuntu 24.04 silently gets Python 3.12 — above the newest interpreter that branch
targets. Separately, an operator migrating a client's database cannot reproduce that client's exact
interpreter, which is what makes a migration rehearsal trustworthy. One authoritative, cited matrix that
code and docs both derive from fixes all of this, and a documented re-verification procedure means the next
support question is answered by running a script rather than by re-reading eight versions of the Odoo
documentation.

## What Changes

- Declare **one authoritative support matrix** as pure data in `models.py`: supported host OS, the tool's own
  Python floor, and per-Odoo-version Python range (minimum **and** maximum), recommended interpreter, and
  PostgreSQL minimum. Every operator-facing surface derives its support statements from it.
- Add **per-version Python maxima**, which the tool does not model today, each carrying its evidence tier:
  `official` (Odoo 19 declares `MAX_PY_VERSION = (3, 14)` in `odoo/release.py`), `derived` (the newest
  interpreter bucket in that branch's `requirements.txt`, whose comments name the target distribution —
  Jammy, Noble, Trixie, Resolute), or `untested` (Odoo 12/13 declare no ceiling at all). The tier is part of
  the data, not a footnote, because only one version states a ceiling outright.
- Add a **recommended interpreter per version** and make it a *default, not a mandate*: the operator can
  always choose another interpreter, and the flow shows the recommendation next to the choice.
- **Workspace venv interpreter selection**: workspace generation checks the host `python3` against the
  version's range. In range, it stays the default. Out of range, the preview warns naming both the range and
  the detected version, and offers a matching `uv`-provisioned interpreter — the strategy already accepted
  for migrations in F3. `uv` is already a `provision check` row and a documented host prerequisite; nothing
  is installed by Python.
- **Migration per-step interpreter override**: the operator can pin any chain step to an exact interpreter —
  above all the source step, to rehearse the migration on the client's own Python — while every other step
  keeps the recommended one. The matrix supplies the recommendation and validates the override against the
  step's range.
- Correct the **PostgreSQL floor for Odoo 19** (12 → 13), record that Odoo 12/13 declare none, and have
  `provision check` report the **installed PostgreSQL version against the floor** of the versions in play
  instead of only reporting that PostgreSQL exists and runs.
- Cite the **Odoo 15/16 Python floor (3.7)**, previously an uncited assumption, and record the **Odoo 14
  divergence**: its documentation says "Python 3.7 or later" while its `setup.py` declares `>=3.6`.
- **Narrow the supported host from "the Debian/Ubuntu apt family" to Ubuntu 22.04 and 24.04**, in both
  `provision check` detection and `provision apply` refusal. **BREAKING**: a Debian host the apt-family check
  previously accepted is now reported, and refused by `apply`, as unsupported. Dropping Debian keeps the
  matrix honest — it was never validated — rather than implying coverage nobody tested.
- Docs: a new `docs/support-matrix.md` carrying the matrix with a **source URL and verbatim quote per fact**
  plus the **re-verification procedure**, and a small stdlib **verification script** that re-derives the
  matrix from the official sources and diffs it against the declared data, so a future session repeats the
  research by running one command. The procedure is part of the deliverable because the research is
  genuinely error-prone: the Odoo documentation URL layout changes across version eras, the Odoo 13 install
  page is a contentless stub, and the pages state no maxima — the answer lives in the repository, not the
  manual.

Out of scope: changing which Odoo versions the tool supports (12–19 stays), supporting non-Ubuntu hosts,
installing or pinning PostgreSQL to a version of the tool's choosing (it still takes the distro's), and the
CI workflow that will exercise the declared Python range (backlog item, unblocked by this change but not
part of it).

## Capabilities

### New Capabilities
- `support-matrix`: the single authoritative, evidence-tiered declaration of what the tool supports — host
  OS, the tool's own Python floor, and per-Odoo-version Python range, recommended interpreter and PostgreSQL
  minimum — which every other surface derives from, which the docs cite fact by fact, and which a script can
  re-derive from the official sources.

### Modified Capabilities
- `provision-check`: package-family detection narrows from the Debian/Ubuntu apt family to the matrix's
  supported Ubuntu releases; PostgreSQL readiness gains a version-against-floor signal.
- `provision-apply`: the "Debian/Ubuntu family only" refusal narrows to the matrix's supported Ubuntu
  releases.
- `workspace-generation`: per-instance venv creation checks the host interpreter against the version's range
  and offers a matching `uv` interpreter when it is out of range.
- `migration-environment`: the per-step interpreter becomes a recommended default that the operator may
  override per step, validated against that step's range.

## Impact

- **Code**: new matrix facts + lookup helpers in `models.py` (pure data; layer contract unchanged);
  `provisioning.py` rows (Ubuntu release detection, PostgreSQL version vs floor); `system.py` probes for the
  Ubuntu release, the PostgreSQL server version and available `uv` interpreters; `planners.py` venv plans
  gain interpreter selection; `workflows/workspace.py` and `workflows/migration.py` prompt for the choice;
  `workflows/provision.py` refusal message.
- **Tooling**: a stdlib-only `tools/verify_support_matrix.py` (network-reading, never imported by the
  package) that re-derives the matrix from `odoo/release.py`, `setup.py`, `requirements.txt` and the
  documentation pages, and reports drift against `models.py`.
- **Docs**: new `docs/support-matrix.md`; `README.md`, `docs/provisioning.md`,
  `docs/configuration-reference.md`, `docs/migration.md` and `docs/wsl-setup.md` point at it instead of
  restating bounds; `CONTRIBUTING.md` gains the re-verification command; `CHANGELOG.md`; `docs/roadmap.md`.
- **Dependencies**: none added. The matrix is stdlib data; `uv` stays a detected host prerequisite.
- **Spec hygiene** (folded in because this change already edits four of the files): all nine capability specs
  still carry the placeholder `## Purpose` that `openspec archive` wrote, which `openspec validate --specs`
  warns about on every run. Replace them with real purposes.
- **Not verifiable on the reference host**: every Ubuntu 22.04 row (this is a 24.04 box — the 22.04 column
  comes from `packages.ubuntu.com` and needs a jammy host or container to confirm), and the end-to-end claim
  that a workspace built on a `uv`-provisioned interpreter actually serves for each version, which needs a
  real build and run per version. The Odoo 19 PostgreSQL 13 floor is satisfied by 24.04's PostgreSQL 16 and
  is verifiable here.
