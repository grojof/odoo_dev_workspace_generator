## Why

Generating a workspace (F1) assumes the Linux host already has PostgreSQL, the Odoo build dependencies, and
optional tooling (wkhtmltopdf, Node + rtlcss). During F1's WSL acceptance those had to be installed by hand.
The `provision` section automates that first mile: it reports what a host is missing and installs/configures
it, so a fresh Linux box (bare server, WSL, or container) becomes Odoo-ready without hand-run apt commands —
while staying optional (anyone whose host is already set up skips it entirely).

## What Changes

- Add a **`provision check`** flow: a read-only host-readiness report (a table of capability → state → detail)
  covering the OS/package family, the Odoo build dependencies, PostgreSQL (installed / running / a usable dev
  role), wkhtmltopdf (present + patched build), Node + rtlcss, and the system Python for dev versions.
- Add a **`provision apply`** flow: install/configure the missing capabilities through previewed, idempotent
  plans (system + build packages; PostgreSQL install/enable + a dev role; the Odoo-recommended patched
  wkhtmltopdf, verified by SHA-256; optional Node + rtlcss). Requires root/sudo and says so.
- Provisioning is **host-agnostic** (not WSL-specific) but **package-manager-specific**: v1 targets the
  **Debian/Ubuntu (apt) family**, detected from `/etc/os-release`; a non-apt host is reported and refused
  cleanly rather than guessed at.
- Reuse the plan → preview → apply contract and pure planners; wire `workflows/provision.py`.

Every package set, the PostgreSQL role command, and the wkhtmltopdf version rule are anchored to official
sources (Odoo "Source install", the Odoo wkhtmltopdf wiki), and match what F1 acceptance validated by hand.

## Capabilities

### New Capabilities
- `provision-check`: read-only detection of host readiness for Odoo development, rendered as a capability
  table (state ∈ OK / MISSING / WARN), changing nothing.
- `provision-apply`: install and configure the missing capabilities (apt build deps, PostgreSQL + dev role,
  patched wkhtmltopdf, optional Node + rtlcss) via previewed, idempotent, root-gated plans.

### Modified Capabilities
<!-- None. Provision is additive and independent of the workspace capabilities. -->

## Impact

- **Code**: extend `odoo_dwg/planners.py` (or a `provision` planner module) with pure builders for each
  capability; add host probes to `system.py` (apt family, package presence, wkhtmltopdf version, PostgreSQL
  running/role, node/rtlcss); wire `workflows/provision.py` (check table + apply flow); a wkhtmltopdf asset
  table with pinned SHA-256 per OS codename.
- **Host tools orchestrated**: `apt-get`, `dpkg`, `systemctl`/`service`, `sudo -u postgres psql`/`createuser`,
  `curl`, `sha256sum`, `npm`. Root/sudo required for `apply`.
- **Tests**: unit-test the planners (rendered command sets per capability) and the check-table logic with
  injected probe results — no apt, no shelling out, no live PostgreSQL.
- **Docs**: `docs/provisioning.md` (what it installs, official sources, apt-family scope) + README map update.
- **Scope / flags**: apt family only for v1 (non-apt hosts refused with a clear message); per-version Python
  interpreters for *migration* (uv/deadsnakes/Docker) are **out of scope here** — they belong to F3.
- Validated by F1's WSL acceptance (the exact package set, PostgreSQL role, and Odoo build all succeeded on
  Ubuntu 24.04 / Python 3.12).
