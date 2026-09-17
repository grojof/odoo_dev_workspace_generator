---
type: explanation
title: "Roadmap (F0–F4) and backlog"
description: "Phased delivery plan and the parked backlog for the Odoo dev/migration workspace generator."
audience: [contributor]
updated: 2026-09-17
---

# Roadmap

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
patched wkhtmltopdf, optional Node + rtlcss); root-gated, and since the support matrix landed it targets
the declared Ubuntu releases rather than the whole apt family. Accepted on WSL.

## F3 — Migration ✅ (accepted)

OpenUpgrade 12→19: per-version clones + `uv` venvs (matched interpreter) + per-step `odoo.conf` + checkpointing
`run_migration.sh`; Docker fallback for the Odoo-13 (Python 3.6) step. Interpreter decision closed with WSL
data (uv floor 3.8). Accepted on WSL: Odoo 15 runs on uv Python 3.8; driver passes `bash -n`.

Extended after acceptance (both archived changes, accepted on WSL): **migration preflight & Docker
readiness** (`2026-07-18-add-migration-preflight` — provision rows for uv/Docker, preflight menu action +
driver-embedded checks, per-version `addons/odoo<major>/{custom,oca}` layout) and **custom-module staging**
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
  [`docs/wsl-setup.md`](wsl-setup.md) covers getting the tool onto a host.
- **F4 — Optional AI emitters** — opt-in, text-only emitters (CLAUDE.md / skills / agents for a user's
  assistant), never installing runtimes, never a default. A parked proposal exists:
  `openspec/changes/add-ai-emitters/` — fill it forward with `/opsx:` and apply.
- **Workspace shallow-clone option** — an opt-in `--depth 1` for dev workspace clones. F1 acceptance showed a
  full single-branch Odoo clone is ~394 MB; some users want history, some want speed. Add a profile flag.
  (Migration clones already use `--depth 1`.) Candidate for a small OpenSpec change.
- ~~CI workflow~~ — **not planned for now** (decided 2026-09-17). The case for it was testing the declared
  Python floor, which the reference box does not run — but that costs a fraction of a second locally
  (`PYTHONPATH=. uv run --python 3.10 --with pytest --no-project pytest -q`, now in `CONTRIBUTING.md`), so
  four runners would buy ceremony rather than safety on a single-developer repo. Cost was never the
  obstacle: this repo is private, so minutes come out of the account allowance, but each job rounds up to a
  whole minute and the whole matrix would bill roughly 5–6 minutes per push — a few percent of a free tier.
  The one thing with no local substitute is drift in the support matrix, which is triggered by *Odoo*
  changing, not by this repo; a scheduled job was considered and dropped because GitHub disables scheduled
  workflows in repos with 60 days of inactivity, which is precisely when the alert would matter.
  `tools/verify_support_matrix.py` is a documented manual habit instead. Revisit if more people contribute
  (then PR gating earns its keep) or if the repo goes public (Actions is free there).
- **VSCode official-extension emitter** — optional static emitter for the official `Odoo.odoo` extension:
  `odools.toml` profiles (verified schema: `[[config]]` + `name`/`extends`/`odoo_path`/`addons_paths`/
  `python_path`, vars `${workspaceFolder}`/`${detectVersion}`/`$autoDetectAddons`), an OWL `jsconfig.json`,
  stylelint wiring, and recommending `Odoo.odoo` in `extensions.json` (replacing the community pick).
  **Deferred until the sibling VSCode extension stabilizes the format** — the dynamic logic (profiles,
  version switching, doctor) lives there, this emitter stays static. Sibling project (WIP):
  [grojof/odoo-ls-companion](https://github.com/grojof/odoo-ls-companion).
- **Provision password-auth mode** — instead of loopback `trust`, create the PostgreSQL role with a password
  and write `db_password` into the workspace `odoo.conf` (needs an `odoo.conf` password field). Safer for
  shared/remote PostgreSQL; the current trust is dev-only. (Deferred open question from F2 design.)

## Validation / refinement (host-dependent)

- ~~Migration overrides tuning~~ — **done** (2026-07-18): 14/15 install clean on 3.8; 16/17 needed the
  `--overrides` lift to `gevent==22.10.2`/`greenlet==2.0.2` (validated by real `uv pip install` on WSL).
- **12/13 OpenUpgrade command shape** — the recipe now runs the ≤ 13 *fork's* own `odoo-bin` from the
  mounted clone with `openupgradelib` installed on the fly (verified on WSL against `odoo:13.0`: container
  reaches OpenUpgrade code against the shared PostgreSQL). Remaining: semantic validation with a real
  legacy database (a synthetic dump cannot migrate).
- **Full 12 → 19 data migration** — run the checkpointing driver end to end on WSL. No longer blocked on a
  client dump: build the source database with **Odoo 12's own demo data** (create a database from the
  `odoo:12.0` image with demo data enabled, then dump it). That is a real Odoo 12 database rather than a
  synthetic one, so it can actually migrate, and it makes the run reproducible for anyone. The same run
  answers two open questions at once: whether the 12/13 steps can run natively on `uv`'s 3.8 floor instead
  of the Docker fallback (their requirements buckets reach `>= '3.8'` but name no distribution, so the
  matrix marks that ceiling `untested`), and whether each step's recommended interpreter holds against real
  data. Docker Engine is installed *in the Linux host itself* by `provision apply` (`docker.io`) — no Docker
  Desktop dependency; `odoo:12.0`/`odoo:13.0` tags verified still pullable (2026-07-18).
- **Confirm the Ubuntu 22.04 column of the support matrix** — its system Python (3.10) and PostgreSQL (14)
  are read from `packages.ubuntu.com`, not from a running jammy host. Needs a 22.04 host or container, which
  the CI item above would also provide.
- ~~Workspace venv on a `uv`-provisioned interpreter~~ — **done** (2026-09-17): an `acme` workspace with
  Odoo 14 + 18 was generated and applied on WSL Ubuntu 24.04. The out-of-range version built on `uv`
  Python 3.8.20 and the in-range one on the host's 3.12.3; both requirement sets installed **without
  overrides** (unlike the migration path, which needs them at 3.10), and `odoo-bin --version` runs in each
  venv. Remaining for a full serve check: the generated profile's `db_user` defaults to the workspace name,
  so serving needs a PostgreSQL role of that name — `provision apply` creates whichever role you name.
- **VSCode `launch.json` debug shape** — confirm the debugpy + `odoo-bin` launch config attaches against a
  real run on WSL (F1 open question).
