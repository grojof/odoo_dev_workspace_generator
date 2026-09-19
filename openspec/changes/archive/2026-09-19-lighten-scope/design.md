# Design

## Context

See `proposal.md` — Why. Measured on the reference box on 2026-09-19: the workspace clones `odoo-14.0` and
`odoo-18.0` are 4.2 GB and 5.7 GB, of which 3.4 GB and 4.7 GB is `.git`; the migration surface's `--depth 1`
clones of the same branches are 0.9 GB and 1.3 GB. A local test confirmed that `git pull --ff-only` advances a
`--depth 1` clone to the new head and that `git fetch --unshallow` restores the complete history afterwards.

## Goals / Non-Goals

**Goals:**

- Make the tool lighter to run (disk and first clone) and lighter to maintain (fewer options, one host, one
  Python floor), without losing anything a user of a development workspace relies on.
- Record *why* each dropped item was dropped, so the decision survives the next backlog review.

**Non-Goals:**

- Migrating existing clones. A full clone keeps working; converting it would be a destructive operation for no
  functional gain.
- Revisiting the migration surface, whose clones are already shallow.

## Decisions

### D1: Shallow by default, no option

A profile flag would be one more field to validate, document and test, for a choice almost nobody changes. The
default that fits a development workspace is shallow; the escape hatch — `fetch --unshallow` — is a single git
command, documented where the workspace layout is described. OCA clones follow the same rule.

*Alternative considered:* a `shallow_clone` profile field. Rejected on the maintenance argument above.

### D2: One host, and the floor that follows from it

With 24.04 the only supported host, the tool's floor is its system Python, 3.12. Everything that existed only to
honour 3.10 goes: the separate 3.10 test run in `CONTRIBUTING.md` and `CLAUDE.md`, the `importorskip` around
`tomllib`, the 3.10 classifier. The ruff target moves to `py312`; any rule that newly fires is fixed as part of
this change rather than suppressed.

The wkhtmltopdf asset map keeps only the entry the supported host uses (`noble`, which maps to the upstream
`jammy` build, as before). Entries for hosts `provision apply` now refuses are unreachable data.

### D3: Dropped items keep their reasons

The roadmap does not simply lose the two items: each becomes a struck-through line saying it was dropped and
why, as the CI decision already does. `trust` on loopback is documented in `docs/provisioning.md` as a
deliberate choice for local development, with the manual steps for anyone who needs password authentication.

## Risks / Trade-offs

- **A 22.04 developer loses support** → the check reports it clearly and `apply` refuses before running
  anything; nothing is half-applied. The decision can be revisited with a real 22.04 validation.
- **Someone relied on history in the shared clone** (`git log` / `blame` in the Odoo source) → one documented
  command restores it, and existing full clones are left as they are.
- **Raising the floor could hide a 3.10-only regression** → there is no 3.10 host left to regress on; the
  supported configuration is exactly what the suite runs.

## Migration Plan

New clones are shallow on the next generation; existing ones are untouched. Operators on 22.04 see the host
reported as unsupported by `provision check`.
