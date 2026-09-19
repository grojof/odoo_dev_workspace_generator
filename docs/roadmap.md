---
type: explanation
title: "Roadmap (F0–F4) and backlog"
description: "Phased delivery plan and the parked backlog for the Odoo dev/migration workspace generator."
audience: [contributor]
updated: 2026-09-19
---

# Roadmap

**Released: v0.1.0 (2026-09-19).** F0–F3 are complete; see [`CHANGELOG.md`](../CHANGELOG.md).

Delivery is phased so each phase is independently useful and verifiable. Non-trivial work is proposed and
tracked through OpenSpec (`/opsx:*`); every phase below was accepted end-to-end on WSL Ubuntu 24.04.

## F0 — Foundation ✅

Package skeleton mirroring `odoo_instance_manager`, OpenSpec + `CLAUDE.md`, i18n (English/Spanish), CLI/menu.

## F1 — Workspace ✅ (accepted E2E)

JSON profile → shared repo cache, per-instance venv, `addons-custom`/per-version `addons-oca`, per-version
`odoo.conf`, VSCode files, per-workspace README; create-only vs manage-only over plan → preview → apply.
Accepted on WSL: a generated Odoo 18 workspace served HTTP 200 at `/web/login`.

## F2 — Provision ✅ (accepted E2E)

`check` (host-readiness table) + `apply` (build deps, PostgreSQL + dev role + loopback trust, checksum-verified
patched wkhtmltopdf, optional Node + rtlcss); root-gated, and it targets Ubuntu 24.04 only (the whole apt family until the
support matrix, then 22.04/24.04 until `lighten-scope`). Accepted on WSL.

## F3 — Migration ✅ (accepted)

OpenUpgrade 12→19: per-version clones + `uv` venvs (matched interpreter) + per-step `odoo.conf` + checkpointing
`run_migration.sh`. Every step runs natively in a `uv` venv; the Docker fallback the Odoo 13 step first used
was removed in `drop-docker-run-13-natively`. Interpreter decision closed with WSL data (uv floor 3.8). Accepted on WSL: Odoo 15 runs on uv Python 3.8; driver passes `bash -n`.

Extended after acceptance (both archived changes, accepted on WSL): **migration preflight**
(`2026-07-18-add-migration-preflight` — provision rows for uv (and Docker, since removed), preflight menu
action + driver-embedded checks, per-version `addons/odoo<major>/{custom,oca}` layout) and **custom-module staging**
(`2026-07-18-add-custom-module-staging` — `odoo-module-migrator` orchestration, analysis-file findings,
inert scaffolds, per-module report). Environment cleanup landed alongside (`Clean a migration environment`).

---

# Backlog (next sessions)

Parked work, ordered roughly by value. Spec-driven items have (or should get) an OpenSpec change; validation
items are host-dependent.

## Features (OpenSpec)

- ~~Support matrix~~ — **done** (2026-09-17, change `add-support-matrix`): one authoritative,
  evidence-tiered matrix in `models.py` + [`docs/support-matrix.md`](support-matrix.md), with
  `tools/verify_support_matrix.py` to re-derive every bound from its official source. Hosts narrowed to
  Ubuntu 22.04/24.04 (BREAKING for Debian); tool Python floor 3.10; per-version Python maxima added
  (derived from each branch's own `requirements.txt` buckets, cross-validated against Odoo 19's declared
  `MAX_PY_VERSION`); Odoo 19's PostgreSQL floor corrected to 13. Interpreter choice now exists in both the
  workspace and migration flows. Development of this repo moved into WSL (clone under `~`, not `/mnt/c`);
  [`docs/wsl-setup.md`](wsl-setup.md) covers getting the tool onto a host. `lighten-scope` later narrowed the
  hosts to Ubuntu 24.04 alone and raised the tool's floor to 3.12.
- ~~F4 — Optional AI emitters~~ — **dropped** (2026-09-19, change `lighten-scope`). Emitting `CLAUDE.md`,
  skills or other assistants' rules files would couple the tool to formats that change month to month, one per
  assistant, while the per-workspace README already gives any assistant its context without coupling to one.
  The parked proposal was deleted. Revisit only if one format becomes a stable, cross-assistant standard.
- ~~Workspace shallow clones~~ — **done** (2026-09-19, change `lighten-scope`), as the default and without a
  profile option. The earlier note here (a full clone "~394 MB") was wrong by an order of magnitude: measured
  full single-branch clones were 4.2 GB (Odoo 14) and 5.7 GB (Odoo 18), almost all history; shallow ones are
  0.9 and 1.3 GB. `git fetch --unshallow` restores history for whoever needs it, and refreshing still works.
- ~~CI workflow~~ — **not planned for now** (decided 2026-09-17). The case for it was testing the declared
  Python floor, which the reference box did not run; since `lighten-scope` the floor (3.12) *is* the reference
  box's Python, so that case is gone, and runners would buy ceremony rather than safety on a
  single-developer repo. Cost was never the
  obstacle: this repo is private, so minutes come out of the account allowance, but each job rounds up to a
  whole minute and the whole matrix would bill roughly 5–6 minutes per push — a few percent of a free tier.
  The one thing with no local substitute is drift in the support matrix, which is triggered by *Odoo*
  changing, not by this repo; a scheduled job was considered and dropped because GitHub disables scheduled
  workflows in repos with 60 days of inactivity, which is precisely when the alert would matter.
  `tools/verify_support_matrix.py` is a documented manual habit instead. Revisit if more people contribute
  (then PR gating earns its keep) or if the repo goes public (Actions is free there).
- ~~Official Odoo extension support~~ — **done** (2026-09-19, change `use-official-odoo-language-server`).
  Workspaces recommend the official `Odoo.odoo` extension instead of a third-party one, turn Pylance off so
  Python is analysed once, and carry an `odools.toml` with one profile per version ≥ 14 using only the four
  documented minimal keys as absolute paths. No `jsconfig.json`: OdooLS 1.5 handles JavaScript and OWL from
  the manifests' asset bundles. A richer emitter was dropped — the official extension already provides
  profiles, per-version switching and a configuration view — and `tools/verify_odools_config.py` plus
  [`docs/editor-integration.md`](editor-integration.md) keep the emitted file in step with new releases.
  Validated by running the official OdooLS binaries (1.4.0 stable and 1.5.2 beta) against a generated
  workspace. Open: whether to adopt any 1.5 key once 1.5 reaches the stable channel.
- ~~Provision password-auth mode~~ — **dropped** (2026-09-19, change `lighten-scope`). It serves shared or
  remote PostgreSQL, which a local development tool does not target, and it would add secret generation and
  storage, a plaintext password in `odoo.conf` and new `pg_hba` rules — a security surface with no user.
  Loopback `trust` is documented as intentional in `docs/provisioning.md`, with the manual steps if needed.
- ~~Outbound firewall and mail capture~~ — **done** (2026-09-19, change `add-egress-control`). The need was
  testing and migrating copies of production without mailing customers or calling real services. The choice
  was host-level control, since Odoo's `neutralize` is version-bound and blind to custom addons:
  - **OpenSnitch:** deny by default, ask when its window is open, and log every decision to the journal;
  - **Mailpit:** local mail capture.
  
  Both are opt-in in `provision`, pinned and verified, and can be turned off or on, or uninstalled, from its
  menu. A spike and the operator's own test on WSL drove every non-default setting (`proc` monitoring,
  `InterceptUnknown`, fail closed, the journal logger) and the rule order that keeps `odoo-bin` on localhost.
  See [`egress-control.md`](egress-control.md).
## Validation / refinement (host-dependent)

- ~~Migration overrides tuning~~ — **done** (2026-07-18): 14/15 install clean on 3.8; 16/17 needed the
  `--overrides` lift to `gevent==22.10.2`/`greenlet==2.0.2` (validated by real `uv pip install` on WSL).
- ~~12/13 OpenUpgrade command shape~~ — **done**: — the recipe now runs the ≤ 13 *fork's* own `odoo-bin` from the
  mounted clone with `openupgradelib` installed on the fly (verified on WSL against `odoo:13.0`: container
  reaches OpenUpgrade code against the shared PostgreSQL). **Semantic validation done** (2026-09-17): the
  step migrated a real Odoo 12 demo database to 13.0 and checkpointed, as part of the full 12 → 19 run.
- ~~Full 12 → 19 data migration~~ — **done** (2026-09-17). The source database was built with **Odoo 12's own
  demo data** (a `odoo:12.0` container creating `demo12` against the host PostgreSQL, then `pg_dump -Fc`),
  which is a real Odoo database rather than a synthetic dump and makes the run reproducible for anyone. The
  chain completed on WSL Ubuntu 24.04: eight checkpoints, `[done]`, working database at `base 19.0.1.3` with
  its data intact, `html_editor` installed in place of `web_editor` and the modules Odoo dropped gone. It
  exposed two blocking defects, both fixed in `fix-preflight-coverage-classification`: coverage treating
  Odoo's own renamed/dropped modules as the operator's, and Odoo ≤ 16 needing `setuptools<81` for
  `pkg_resources`. That run still used the Docker fallback for the 13 step; the next item removed it.
- ~~Native 12/13 instead of the Docker fallback~~ — **done** (2026-09-17, change
  `drop-docker-run-13-natively`). Odoo 13 — the only step that ever ran in a container, since Odoo 12 is
  restored and never executed — installs its full requirements on `uv`'s 3.8 with one build constraint
  (`setuptools<58`, for `vatnumber`'s `use_2to3`) and migrates correctly. Testing it also exposed why the
  container path was worse than a workaround: the `odoo:13.0` image's `addons_path` meant the step ran the
  *image's* add-ons, skipping every add-on migration script while reporting success. **Docker is gone from
  the project** — provisioning, preflight and the driver no longer mention it.
- ~~Confirm Ubuntu 22.04~~ — **dropped with the host** (2026-09-19, change `lighten-scope`). It was declared
  but never run on a real host — the reason Debian was dropped — and it pinned the tool at Python 3.10. Ubuntu
  24.04 is the only supported host and the tool's floor is 3.12.
- ~~Workspace venv on a `uv`-provisioned interpreter~~ — **done** (2026-09-17): an `acme` workspace with
  Odoo 14 + 18 was generated and applied on WSL Ubuntu 24.04. The out-of-range version built on `uv`
  Python 3.8.20 and the in-range one on the host's 3.12.3; both requirement sets installed **without
  overrides** (unlike the migration path, which needs them at 3.10), and `odoo-bin --version` runs in each
  venv. The role mismatch this exposed (`db_user` defaulted to the workspace name, a role nobody created) was
  fixed by `default-shared-db-role`: workspaces now default to the shared `odoo` role.
- ~~Manual VSCode check~~ — **done** (2026-09-19) on an Odoo 15 workspace, with the recommended extensions.
  The official extension works and **F5** attaches the debugger in all four generated configurations: server,
  shell, upgrade modules and test module. The first try exposed the `pkg_resources` failure fixed by
  `fix-workspace-venvs`.
- **When OdooLS 1.5 reaches the stable channel** — run `python tools/verify_odools_config.py` and decide whether
  any 1.5 key is worth emitting, following [`editor-integration.md`](editor-integration.md).