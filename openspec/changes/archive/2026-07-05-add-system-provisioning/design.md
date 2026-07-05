## Context

F1 generates workspaces but assumes the host is Odoo-ready. F1's WSL acceptance proved the exact prerequisites
by installing them by hand on Ubuntu 24.04: the apt build-dependency set, PostgreSQL 16 + a login role +
local trust, and (implicitly) the patched wkhtmltopdf for report rendering. F2 turns that manual first mile
into an optional, previewed, idempotent `provision` section, mirroring the sibling app `odoo_instance_manager`
(which already ships validated planners for these exact steps).

## Goals / Non-Goals

**Goals:**
- `provision check`: a read-only host-readiness table, changing nothing.
- `provision apply`: install/configure the missing pieces via plan → preview → apply, idempotent, root-gated.
- Host-agnostic (bare server / WSL / container), anchored to official Odoo sources, matching what F1 validated.

**Non-Goals:**
- Non-apt package managers (dnf/pacman/zypper) — v1 is Debian/Ubuntu only; others are refused cleanly.
- Per-version *migration* interpreters (uv/deadsnakes/Docker) — those belong to F3.
- Production hardening (TLS, firewall, fail2ban) — that is the sibling app's job, not this generator's.

## Decisions

- **Capability model**: each capability is a small unit with a `detect()` (host probe → `(state, detail)`)
  and a pure `plan()` (`list[Command]`). `check` runs every `detect()` and renders the table; `apply`
  composes the `plan()`s for the missing/selected capabilities. This keeps detection (I/O) separate from
  planning (pure) and makes both testable. *Alternative:* one monolithic install script — rejected (not
  idempotent, not checkable, not testable).
- **Reuse the sibling's validated artifacts**: the apt build-dependency list and the **pinned patched
  wkhtmltopdf asset table** (0.12.6.1-3 with per-codename SHA-256 for jammy/noble/bookworm/bullseye) are
  ported from `odoo_instance_manager`, which verified them against Odoo's own Dockerfile checksum. Version
  rule: 0.12.5 for Odoo ≤ 14, 0.12.6 for ≥ 15 (official wkhtmltopdf wiki).
- **PostgreSQL dev role + local trust**: `apply` creates a `LOGIN CREATEDB` role idempotently (a `DO $$` guard,
  never failing if it exists) and, for a **development** host, sets `127.0.0.1/::1` in `pg_hba.conf` to
  `trust` so the workspace `odoo.conf` (which uses `db_host=127.0.0.1`, no password) connects — exactly what
  F1 acceptance used. This is a **dev-only convenience** and is flagged as such. *Alternative:* password auth
  + `db_password` in the workspace profile — deferred (see Open Questions).
- **apt-family gate**: `detect_os_release()` classifies the host; a non-Debian/Ubuntu family is reported by
  `check` and refused by `apply`, never guessed. `apply` also requires root (`os.geteuid() == 0`).
- **Provision planners live in `planners.py`** alongside the workspace planners (single pure module, as in the
  sibling); host probes extend `system.py`.

## Risks / Trade-offs

- **Editing `pg_hba.conf` (trust)** weakens local auth → mitigation: only `127.0.0.1/::1` (loopback), only on
  an explicitly dev host, clearly flagged; a future password mode is the production-safe path.
- **wkhtmltopdf asset drift** (a codename without a pinned asset) → mitigation: unmapped codenames resolve to
  "no verified asset" and the tool recommends the distro package or skip, never a guessed URL (sibling
  behavior).
- **apt package-name drift across releases** → mitigation: the set is the one F1 validated on 24.04; probes
  use `dpkg -s` so a re-apply is a no-op.
- **Root requirement** conflicts with the tool otherwise being user-run → mitigation: only `apply` needs root
  and says so; `check` stays unprivileged.

## Migration Plan

Additive and independent of F1. Land probes + planners with unit tests (pure), then the check table and the
apply flow. Acceptance is re-run on the WSL box: on a fresh distro, `provision apply` should reproduce exactly
the state F1's manual setup reached (build deps + PostgreSQL + role + wkhtmltopdf), after which F1 generation
launches Odoo with no hand steps.

## Open Questions

- Password-auth mode: store a `db_password` in the workspace profile and write it into `odoo.conf` instead of
  relying on local trust — cleaner for shared/remote PostgreSQL. Defer to a follow-up once F1's conf grows a
  password field.
- Whether to detect and reuse an existing PostgreSQL major (e.g. 16) vs. always `apt-get install postgresql`
  (which installs the distro default). v1 installs the distro default; revisit if multiple PG majors matter.
