---
type: reference
title: "Workspace layout"
description: "The directory structure odoo_dwg generates for a client workspace and the shared repo cache."
audience: [developer]
updated: 2026-09-19
---

# Workspace layout

`odoo_dwg` generates two things under the base directory (`~/odoo-workspaces` by default): a **shared,
read-only repo cache** reused across workspaces, and one **per-client workspace** tree.

```
~/odoo-workspaces/
├── .repos/                              # shared cache (one clone per version)
│   ├── odoo-17.0/  odoo-18.0/  ...      # git clone --branch <ver> --single-branch
│   └── oca/<repo>-<ver>/ ...            # OCA repos on the matching branch
└── <name>/                             # a client workspace
    ├── addons-custom/                   # your modules
    ├── addons-oca/odoo<major>/<repo>    # per-version symlinks into .repos/oca
    ├── config/odoo<major>.conf          # one config per version
    ├── .venv/odoo<major>/               # one virtualenv per version
    ├── scripts/setup_venv.sh            # (re)build every venv + install requirements
    ├── scripts/run-odoo<major>.sh       # launch one instance
    ├── .vscode/                         # tasks / launch (serve, shell, upgrade, test) / settings / extensions
    ├── <name>.code-workspace
    ├── odools.toml                      # official Odoo language server profiles (Odoo >= 14)
    ├── workspace.json                   # saved profile (used by the manage flow)
    └── README.md                        # full context for humans and AI assistants
```

## Conventions

- **Instance name**: `odoo<major><name>` (e.g. `odoo18acme`).
- **Per-version HTTP port**: `http_port_base + step` per major, ordered by major, so versions never collide
  (e.g. base 8069 → 8069 / 8079 / 8089). The live-chat/bus port is `http_port + 1000`.
- **Composed `addons_path`** (precedence): `addons-custom` → each OCA repo (via its per-version symlink) →
  the shared `odoo/addons`.

The clone command, `addons_path`, and `odoo.conf` keys follow the official Odoo documentation:

- Source install: <https://www.odoo.com/documentation/18.0/administration/on_premise/source.html>
- CLI / `odoo.conf` reference: <https://www.odoo.com/documentation/18.0/developer/reference/cli.html>

## End-to-end validation (WSL Ubuntu 24.04 only)

Generating the files is verified by unit tests on any OS. Actually **building and launching** a workspace is
intrinsically Linux and is validated by hand on WSL Ubuntu 24.04:

```bash
# On the Linux host, after generating the workspace:
cd ~/odoo-workspaces/<name>
bash scripts/setup_venv.sh                      # python3 -m venv + pip install -r requirements.txt
createdb <name>                                 # as the `odoo` role that provision apply creates
bash scripts/run-odoo18.sh                       # odoo-bin -c config/odoo18.conf → serves on its port
```

This step is host-dependent and is **not** run in CI; it is the manual acceptance check for the change.

### What each version's venv uses

On Ubuntu 24.04 (host `python3` 3.12), with the interpreter the tool picks by default. The generation plan and
`setup_venv.sh` apply the same rules. Every row was built and started by
[`tools/verify_workspace_versions.py`](#re-verifying-every-version).
- `base` installed with no errors.
- Each debug configuration in the generated `launch.json` worked: the shell answered an ORM query, a module's
  tests ran and passed, and the upgrade configuration served the login form.

| Odoo | Python | setuptools rule | setuptools resolved | Requirement changes |
|---|---|---|---|---|
| 12.0 | 3.8 (`uv`) | `<58` | 57.5.0 | `python-ldap==3.1.0` instead of `pyldap==2.4.28` |
| 13.0 | 3.8 (`uv`) | `<58` | 57.5.0 | — |
| 14.0 | 3.8 (`uv`) | `<81` | 75.3.4 | — |
| 15.0 | 3.12 (host) | `<81` | 80.10.2 | — |
| 16.0 | 3.12 (host) | `<81` | 80.10.2 | — |
| 17.0 | 3.12 (host) | unpinned | 84.0.0 | — |
| 18.0 | 3.12 (host) | unpinned | 84.0.0 | — |
| 19.0 | 3.12 (host) | unpinned | 84.0.0 | — |

Why each rule exists:

- **Python:** a version runs on the host `python3` when it is inside that version's range in the
  [support matrix](support-matrix.md), which also declares every range. Odoo 14's maximum is below 3.12. Odoo
  12 and 13 state no maximum, but their pinned `gevent` does not build on 3.12. All three default to the
  recommended `uv` interpreter, and you can still pick another one when generating.
- **setuptools `<58` (≤ 13):** `vatnumber==1.2` still passes `use_2to3`, which setuptools 58 removed. setuptools
  below 58 also still ships `pkg_resources`.
- **setuptools `<81` (14–16):** Odoo imports `pkg_resources` at startup, and setuptools 81 removed it. 17 and
  later do not import it, and they start without it.
- **`python-ldap` for Odoo 12:** the branch pins `pyldap==2.4.28`, a fork PyPI marks "DEPRECATED; use
  python-ldap instead", which does not build on `uv`'s Python 3.8. `python-ldap==3.1.0` is what Odoo 13 pins for
  the same `ldap` module. The shared clone's `requirements.txt` is not modified.

"setuptools resolved" is whatever pip picked within the rule on the date in this page's header, not a pin.

A venv built before this rule (Odoo ≤ 16 on Python 3.12 got setuptools 81+) fails at start with
`ModuleNotFoundError: No module named 'pkg_resources'`; fix it with
`.venv/odoo<major>/bin/pip install 'setuptools<81'`, or rebuild the venv.

### Re-verifying every version

Unit tests prove the plan; only a real host proves that each venv builds and Odoo starts. The pins above were
found that way: an Odoo 15 venv failing on F5, then a build of every version from 12 to 19. To repeat it and
refresh the table above:

```bash
python tools/verify_workspace_versions.py              # every supported version
python tools/verify_workspace_versions.py 12.0 15.0    # only these
python tools/verify_workspace_versions.py --keep       # keep the workspace to inspect a failure
```

It generates a throwaway workspace `verifyall` through the tool's own plan, with each version on the
interpreter the tool picks by default. It previews the plan and applies it only after you type `yes`. For each
version it reports the venv's Python and setuptools and installs `base` and `barcodes`, with demo data, into a new database
`verifyall_<major>`. It then runs the generated debug configurations from `.vscode/launch.json` with their
prompts answered:
- **shell:** an ORM query piped in must come back.
- **test module:** `barcodes`' tests must run without failures.
- **upgrade modules:** the server must serve the `/web/login` form.

Afterwards it removes the workspace, its databases and
filestores, and only the shared clones it had to create. It needs network, PostgreSQL with the development role
(`provision apply`) and `uv`, and takes about 15 minutes when nothing is cached.

**When to run it:** after a setuptools or pip major release; when `uv` changes the Python builds it provides;
when a new Odoo version or a new host Python enters the [support matrix](support-matrix.md); and before a
release.

**When a version fails**, rerun only that version with `--keep` and read the failing step in the output.
- **The build fails:** it is almost always one pinned requirement that no longer builds.
- **The start fails:** it is almost always a removed API such as `pkg_resources`.

Fix it the way the existing cases were fixed, in one place in `models.py`, so the plan and `setup_venv.sh`
agree:
- a setuptools bound in `setuptools_requirement`;
- a substitute in `REQUIREMENT_SUBSTITUTES`, but only for a project that its maintainers deprecated in favour
  of a named successor;
- an interpreter default in `resolve_interpreter`.

Record the evidence in the change's `design.md`.

## Editor

The workspace is set up for the **official** Odoo extension (`Odoo.odoo`) and its language server: an
`odools.toml` with one profile per version (switch it from the status bar), Pylance turned off so Python is
analysed once, and no `jsconfig.json`. What is emitted, what is deliberately not, and how to keep up with the
extension's releases: [`editor-integration.md`](editor-integration.md).

## Shared clones are shallow

The Odoo and OCA clones in `<base>/.repos` are made with `--depth 1`: a development workspace never reads the
branch history, and it is most of a clone's size (an Odoo branch is about 5 GB with history, about 1 GB without).
**Refresh shared repos** keeps working on them. If you need `git log` or `git blame` on the Odoo source, fetch
the history once:

```bash
git -C ~/odoo-workspaces/.repos/odoo-18.0 fetch --unshallow
```

Clones made before shallow cloning became the default are left as they are.
