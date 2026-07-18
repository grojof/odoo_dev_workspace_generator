# Design — add-migration-preflight

## Context

The migration mode generates a correct environment but verifies almost nothing before running: Docker is a
text warning, the dump is trusted, the DB version is taken on faith, and non-core addons have no defined
home. The project already has the right shapes to reuse: `provisioning.py` (facts gathered with I/O +
pure row rendering), `system.py` probes, pure planners, and the plan → preview → apply contract.

## Goals / Non-Goals

**Goals**: fail before the migration starts, not during it; one preflight implementation reused by menu,
generate flow, and driver; a defined per-version home for custom/OCA addons; Docker readiness handled by
the same provision machinery as every other host tool.

**Non-Goals**: migrating custom module code (oca-port / odoo-module-migrator); auto-fixing failures
(beyond pointing at the existing provision plans); supporting non-apt hosts; plain-SQL dump conversion.

## Decisions

1. **Docker Engine installs from the distro archive (`docker.io`)**, not Docker's `docker-ce` repo.
   Rationale: zero extra apt sources/GPG keys (consistent with `plan_build_deps`), officially maintained
   by Debian/Ubuntu, and fully sufficient for running two fallback containers. Alternative (docker-ce,
   Docker's official repo) documented in `docs/provisioning.md` for operators who prefer it; the check
   only cares that *a* `docker` binary and daemon respond.

2. **Preflight has two scopes, because DB facts need a live database.**
   - `host` scope (no DB): chain-aware tool checks (`uv`; `docker` binary + `docker info` + image
     presence via `docker image inspect`, only when the chain includes 12/13), PostgreSQL reachable +
     role exists, dump file exists/readable and `pg_restore --list` parses (which also proves custom
     format — plain SQL dumps are rejected with a clear message), addons layout directories exist.
   - `database` scope: actual Odoo version from `ir_module_module` (`base.latest_version`), declared
     source match, installed-module list, per-step coverage (below). It runs against a *named existing
     database* (operator already restored one) from the menu, and inside the driver **right after the
     `00_source` restore, before step 1** — the earliest moment the data exists at all.
   Alternative rejected: restoring the dump to a throwaway DB inside the menu preflight — slow, mutates
   host state from a "check", and duplicates what the driver does seconds later anyway.

3. **Coverage check is per step, against each step's `addons_path`.** For every module installed in the
   DB (state `installed`), each step must find it somewhere in that step's path: target Odoo core,
   OpenUpgrade, `addons/odoo<major>/oca`, or `addons/odoo<major>/custom`. Modules found nowhere are
   reported (WARN, with the exact directory where the operator should place the migrated branch). This is
   the practical definition of "core / OCA / custom" — classification by *where the module is found*,
   not by guessing from name prefixes.

4. **Addons layout mirrors the workspace convention**: `addons/odoo<major>/custom` and
   `addons/odoo<major>/oca` under the environment root, new `MigrationEnv` path helpers, created by the
   tree plan, threaded into each step's conf as custom → OCA → OpenUpgrade → core (first match wins in
   Odoo's module lookup, so operator code takes precedence).

5. **Python preflight + rendered bash preflight share one source of truth.** Menu/generate use a new
   `odoo_dwg/preflight.py` (`gather_host_facts` / `gather_db_facts` with I/O, pure `preflight_rows` for
   the table — the `provisioning.py` pattern). The driver is plain bash on a possibly Python-less
   posture, so `render_run_migration_sh` renders an equivalent `preflight()` bash function (tool checks,
   psql version query, coverage via `test -d`). The duplication is confined to one template function and
   both sides are asserted by the same test expectations.

6. **Auto-invocation is non-interactive and fail-fast.** `Generate a migration environment` runs the
   host-scope preflight first and prints the table; MISSING rows for chain-required tools become a
   confirm-to-continue prompt (the plan may be exactly what fixes them — e.g. venvs — so generation is
   not hard-blocked, but the operator decides informed). The driver aborts on any failed check with a
   non-zero exit before touching the database further.

## Risks / Trade-offs

- [`odoo:12.0`/`odoo:13.0` are delisted and could stop resolving] → image-pull plan failure is loud;
  docs keep the plan-B (build from `odoo/docker` git tags); preflight reports image absence explicitly.
- [`docker` may need root or docker-group membership] → probes report the *permission* failure text
  distinctly from "not installed"; docs cover `usermod -aG docker`.
- [bash/python preflight drift] → both rendered from the same facts list where feasible; template tests
  assert the bash function contains every check the spec names.
- [old `pg_restore` reading newer dumps] → the check runs with the host's client against the operator's
  dump — exactly what the driver will do, so a mismatch surfaces here, which is the point.

## Migration Plan

Pure addition (new menu actions, new rows, new dirs in newly generated envs). Existing generated
environments keep working; regenerating adds the addons layout. No rollback concerns beyond `git revert`.

## Open Questions

- None blocking. Image-tag resolvability and `docker.io` daemon behavior get re-verified on the WSL host
  during apply (acceptance).
