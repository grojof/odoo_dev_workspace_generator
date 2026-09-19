---
type: reference
title: "Support matrix"
description: "What odoo_dwg supports — hosts, Python per Odoo version, PostgreSQL — with the source behind every bound and how to re-verify it."
audience: [developer, contributor]
updated: 2026-09-19
---

# Support matrix

This page is the authority on what the tool supports. The same facts live in code as
`ODOO_SUPPORT` / `SUPPORTED_HOSTS` in [`odoo_dwg/models.py`](../odoo_dwg/models.py), which every surface —
`provision check`, workspace generation, migration environments, the generated per-workspace README — reads
from rather than restating. Change a bound there and here together; nowhere else states one.

Every bound below carries its **evidence tier**, because only one Odoo version states a Python *maximum*
outright:

| Tier | Meaning |
|---|---|
| `official` | Odoo or the distribution states it outright. |
| `derived` | Deduced from an official artifact — the newest interpreter bucket a branch's own `requirements.txt` declares, read through the distribution its comment names. |
| `untested` | No source states it and this project has not validated it. Treated as "no bound", never as "works". |

The tool never presents a `derived` or `untested` bound as an Odoo requirement: it prints the tier alongside
the value.

## Hosts

**One host: Ubuntu 24.04 LTS**, the reference box every end-to-end acceptance runs on. Hosts that were declared
but never run were dropped rather than implied: Debian first, then Ubuntu 22.04 (2026-09-19). `provision check`
reports any other host as unsupported and still completes; `provision apply` refuses before running anything.

| Host | Codename | System `python3` | PostgreSQL |
|---|---|---|---|
| Ubuntu 24.04 LTS | noble | 3.12 | 16 |

Source: [`packages.ubuntu.com/noble/python3`](https://packages.ubuntu.com/noble/python3),
[`/noble/postgresql`](https://packages.ubuntu.com/noble/postgresql).

**The tool's own Python floor is 3.12**, the supported host's system Python, and it matches
`requires-python = ">=3.12"` in `pyproject.toml` (a unit test asserts the two agree).

## Odoo versions

| Odoo | Python min | tier | Python max | tier | Recommended | PostgreSQL min | tier |
|---|---|---|---|---|---|---|---|
| 12.0 | 3.5 | official | — | untested | 3.8 | — | untested |
| 13.0 | 3.6 | official | — | untested | 3.8 | — | untested |
| 14.0 | 3.7 | official¹ | 3.10 | derived | 3.8 | 12.0 | official |
| 15.0 | 3.7 | official | 3.12 | derived | 3.8 | 12.0 | official |
| 16.0 | 3.7 | official | 3.13 | derived | 3.10 | 12.0 | official |
| 17.0 | 3.10 | official | 3.14 | derived | 3.10 | 12.0 | official |
| 18.0 | 3.10 | official | 3.14 | derived | 3.12 | 12.0 | official |
| 19.0 | 3.10 | official | **3.14** | **official** | 3.12 | **13.0** | official |

¹ Odoo 14's sources disagree with its documentation — see [Known divergences](#known-divergences).

**Recommended is not the maximum.** The recommended column is what this project has actually built and run
(measured on the reference box, where `uv`'s installable floor is 3.8); the range is what Odoo declares. That
is why Odoo 15 recommends 3.8 although it tolerates 3.12. The recommendation is a *default*: every flow that
builds an environment lets the operator choose another interpreter, and says so when a choice falls outside
the range.

**An unstated maximum is not a green light.** Odoo 12 and 13 state no ceiling, so no interpreter is ever
*outside* their range — but that is absence of evidence: on 3.12 their pinned `gevent` does not build (measured
2026-09-19). A workspace therefore uses the host `python3` for them only when it is no newer than the
recommendation, and otherwise defaults to the recommended `uv` interpreter.

### Verbatim sources, per version

| Odoo | Quote | Source |
|---|---|---|
| 12.0 | "Odoo requires Python 3.5 or later to run." · "Download and install the latest version of PostgreSQL." (no floor given) | [12.0 install](https://www.odoo.com/documentation/12.0/setup/install.html) |
| 13.0 | `python_requires='>=3.6'` — **its install page contains no requirements text at all** | [`setup.py@13.0`](https://raw.githubusercontent.com/odoo/odoo/13.0/setup.py) |
| 14.0 | "Odoo requires Python 3.7 or later to run." · "supported versions: 12.0 or above" | [14.0 source install](https://www.odoo.com/documentation/14.0/administration/install/source.html) |
| 15.0 | "Odoo requires Python 3.7 or later to run." · "supported versions: 12.0 or above" | [15.0 source install](https://www.odoo.com/documentation/15.0/administration/on_premise/source.html) |
| 16.0 | "Odoo requires Python 3.7 or later to run." · "supported versions: 12.0 or above" | [16.0 source install](https://www.odoo.com/documentation/16.0/administration/on_premise/source.html) |
| 17.0 | "Odoo requires Python 3.10 or later to run." · "Changed in version 17: Minimum requirement updated from Python 3.7 to Python 3.10." | [17.0 source install](https://www.odoo.com/documentation/17.0/administration/on_premise/source.html) |
| 18.0 | "Odoo requires Python 3.10 or later to run." · "supported versions: 12.0 or above" | [18.0 source install](https://www.odoo.com/documentation/18.0/administration/on_premise/source.html) |
| 19.0 | `MIN_PY_VERSION = (3, 10)` · `MAX_PY_VERSION = (3, 14)` | [`odoo/release.py@19.0`](https://raw.githubusercontent.com/odoo/odoo/19.0/odoo/release.py) |
| 19.0 | "Changed in version 19: Minimum requirement updated from PostgreSQL 12 to PostgreSQL 13." · "supported versions: 13.0 or above" | [19.0 source install](https://www.odoo.com/documentation/19.0/administration/on_premise/source.html) |

### How the maxima are derived

No Odoo documentation page states a maximum Python. The answer is in each branch's `requirements.txt`, which
splits its pins into buckets by `python_version` and **names the target distribution in the comment**. The
newest such bucket is the newest interpreter that branch is maintained for:

| Odoo | Newest bucket, verbatim | Distribution | ⇒ max |
|---|---|---|---|
| 14.0 | `gevent==21.8.0 ; python_version > '3.9'  # (Jammy)` | Ubuntu 22.04 | 3.10 |
| 15.0 | `gevent==24.2.1 ; sys_platform != 'win32' and python_version >= '3.12'  # (Noble)` | Ubuntu 24.04 | 3.12 |
| 16.0 | `PyPDF==5.4.0 ; python_version >= '3.13' # (Trixie)` | Debian 13 | 3.13 |
| 17.0 | `greenlet==3.3.2 ; sys_platform != 'win32' and python_version >= '3.14'  # (Resolute)` | Ubuntu 26.04 | 3.14 |
| 18.0 | same Resolute bucket | Ubuntu 26.04 | 3.14 |
| 19.0 | same Resolute bucket | Ubuntu 26.04 | 3.14 |

**Why trust this derivation:** Odoo 19 is the only version that also declares its ceiling outright, and the
derivation reproduces it exactly (`MAX_PY_VERSION = (3, 14)` ⇔ the Resolute bucket). A rule that gets the one
checkable case right is the best available answer for the ones that state nothing.

Odoo 12 and 13 have open-ended `>= '3.7'` / `>= '3.8'` buckets that name **no** distribution, so they get no
ceiling — tier `untested`. Odoo 13 is nevertheless known to *run* on `uv`'s 3.8 floor: its requirements
install there and a 12 → 13 migration completes (measured 2026-09-17), which is what lets every step run
natively. That is a floor result, not a ceiling: nothing says where the branch stops working, so the bound
stays `untested`. Odoo 12 is never executed by a chain at all.

### Known divergences

- **Odoo 14: documentation 3.7 vs `setup.py` `>=3.6`.** The matrix carries the stricter documented floor,
  3.7. The verification script knows both readings and reports the disagreement rather than treating it as
  drift.
- **Community reports are not used as bounds.** The most-cited threads for "Odoo 16 cannot run on Python
  3.11" and "Odoo 17 fails on Python 3.12" turn out to be a macOS `psycopg2` linking error
  (`no LC_RPATH's found`) and an uninitialised database — neither is an interpreter ceiling, and the
  repository data contradicts the conclusion both reach. They are useful as symptom references, nothing more.

## Re-verifying this page

```bash
python tools/verify_support_matrix.py            # every version and both hosts
python tools/verify_support_matrix.py 18.0 19.0  # only these versions
```

The script re-derives every bound from the sources below and exits non-zero on drift, naming the version,
the fact, both values and the source URL. It never edits the declared matrix: fixing drift means editing
`odoo_dwg/models.py` **and** this page together. It is stdlib-only, lives outside the package
(`odoo_dwg` never imports it) and outside the unit suite, and is the only file in the repository that reaches
the network.

### Source precedence, per fact

| Fact | Primary | Secondary |
|---|---|---|
| Python minimum | `raw.githubusercontent.com/odoo/odoo/<v>/odoo/release.py` → `MIN_PY_VERSION` (19.0 only), then `.../setup.py` → `python_requires` | the version's source-install page |
| Python maximum | `.../odoo/release.py` → `MAX_PY_VERSION` (19.0 only) | `.../requirements.txt` → newest `python_version` bucket + the distribution its comment names |
| PostgreSQL minimum | the version's source-install page → "supported versions: N.0 or above" | — |
| Host `python3` / PostgreSQL | `packages.ubuntu.com/<codename>/python3` and `/postgresql` | — |

**The repository is primary, the manual secondary.** The manual states no maxima, and it has a hole exactly
where you would not look for one (13.0).

### Documentation URL layout

The path changed twice across the supported range, so it must be resolved per version rather than assumed
(`odoo_docs_url()` in `models.py` does this):

| Versions | Path |
|---|---|
| 12.0, 13.0 | `/documentation/<v>/setup/install.html` |
| 14.0 | `/documentation/<v>/administration/install/source.html` |
| 15.0 – 19.0 | `/documentation/<v>/administration/on_premise/source.html` |

### Traps, all of them hit while producing this page

1. **A summarising web fetcher returns empty content for every pre-17 documentation page while reporting
   success.** Retrieve the HTML directly and strip the tags locally.
2. **The Odoo 13.0 install page is a table-of-contents stub** with no requirements text, so a
   documentation-only method has a silent hole. Use `setup.py` for that version.
3. **Splitting text on `.` shreds "Python 3.10".** Match `Python 3\.\d+` and
   `supported versions?: \d+\.\d+` as patterns instead.
4. **Codename → Python must come from the distribution, not from memory.** Jammy 3.10, Noble 3.12,
   Resolute 3.14 are all read from `packages.ubuntu.com`; Trixie (Debian 13) is 3.13.
5. **`>=` and `<` buckets are not symmetric.** Only an open-ended upper bucket (`>=` / `>`) says what a
   branch targets; a `< '3.12'` bucket is the *older* half of a split and means nothing about the ceiling.

## What the tool does with this

- **`provision check`** reports the host release against the supported list, the installed PostgreSQL server
  against the floor of the versions in play, the host `python3`, and which interpreters `uv` can provide.
- **`provision apply`** refuses any host outside the supported releases, before assembling a single command.
- **Workspace generation** builds each instance's venv with the host `python3` when it is inside that
  version's range; when it is not, it says so — naming the range, the detected version and the evidence tier
  — and offers a matching `uv`-provisioned interpreter instead (`uv venv --seed`, so the venv still has
  `pip` and everything downstream is unchanged).
- **Migration environments** take each step's interpreter from the recommendation, and let the operator pin
  any step to a specific Python. A pinned step's requirements repair follows the interpreter actually in use.
  Every step runs natively on a `uv` interpreter, including Odoo 13, so no chain needs a container runtime.

## See also

- [`provisioning.md`](provisioning.md) — the host readiness table and what `apply` installs.
- [`migration.md`](migration.md) — chains, interpreters and the two OpenUpgrade layouts.
- [`configuration-reference.md`](configuration-reference.md) — the workspace profile.
- [`roadmap.md`](roadmap.md) — the open validation items this page depends on.
