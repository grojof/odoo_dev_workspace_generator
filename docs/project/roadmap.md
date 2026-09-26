---
type: explanation
title: "Roadmap and backlog"
description: "Phased delivery plan and the parked backlog for the Odoo dev/migration workspace generator."
tags: [roadmap, backlog, project]
audience: [contributor]
updated: 2026-09-25
---

# Roadmap

**Released: v0.2.0 (2026-09-20).** F0–F3 are complete; see [`CHANGELOG.md`](../../CHANGELOG.md).

**What 0.2.0 brought:** the outbound firewall and mail capture (change `add-egress-control`);
`harden-for-0-2-0`, which closed what repeated pre-release audit rounds found (each round one docs review and
one code review, both verified by hand before anything was changed); and `read-pg-hba-from-the-server`, which
ended the longest-running of them by asking PostgreSQL for its own rules instead of re-implementing its
parser. What the audits found:
- injection through versions and profiles, now validated at every entry point;
- a migration driver that skipped its coverage check entirely and trusted checkpoints from another attempt;
- coverage and `apriori.py` looked up in the wrong place for the ≤ 13 steps;
- probes that could ask for a password, and host changes that were wider than they needed to be
  (loopback `trust` for every role, the firewall's DNS rule on every port, root downloads in `/tmp`);
- plans that printed every line: one line per step now, with `--verbose` to see everything;
- a checkpoint that reported success after `pg_dump` failed, so a whole chain could run with no recovery
  point; plan steps that inherited the operator's stdin (and `apt` dialogs that could hang behind captured
  output); `pg_hba.conf` never narrowed on a host that was already provisioned; and the firewall's
  `odoo-bin` rejection sorting after two allow rules;
- a host with PostgreSQL stopped reported as fully provisioned, because a probe that could not answer was
  read as "nothing to do"; a blanket loopback `trust` spelled `localhost` surviving the narrowing while the
  check called it narrowed; and Odoo 12's requirements installing only the `python-ldap` substitute while
  reporting success, because a pipeline hid `grep`'s failure;
- a migration step that ran with no OpenUpgrade code on disk and still reported `[done]`, a failing step
  that died without naming itself, and blanket `trust` lines that survived when indented, written
  `hostnossl` or in `address netmask` form — and then the realisation that the address was never the right
  test at all: `all`, `0.0.0.0/0` and `127.0.0.0/8` contain loopback without naming it, a role line below a
  rule for every role is never read, and an `include` directive hides rules from the file itself;
- and finally `hostssl` — the rule a loopback connection is matched against on a host with `ssl = on`, which
  the supported one has. Four rounds had each fixed the narrowing correctly and each left it blind somewhere
  else, so the approach changed rather than the pattern: the check reads `pg_hba_file_rules`, apply asks the
  server whether its own rewrite worked, and the verifier asserts against a real cluster. The same round
  also fixed a file with no trailing newline having its last record fused with the inserted rule.

Three verifiers came out of those rounds, all outside the unit suite because it may not shell out:
`tools/verify_migration_driver.py` executes the generated migration driver against stub binaries,
`tools/verify_generated_shell.py` runs ShellCheck over every generated script, and
`tools/verify_pg_hba_trust.py` runs the `pg_hba.conf` rewriter over every shape of that file it must handle
and checks the result against a throwaway PostgreSQL cluster. What each one covers is listed once, in
[`CONTRIBUTING.md`](../../CONTRIBUTING.md) — this page stopped repeating the count after it drifted four rounds
running.

Delivery is phased so each phase is independently useful and verifiable. Non-trivial work is proposed and
tracked through OpenSpec (`/opsx:*`); every phase below was accepted end-to-end on WSL Ubuntu 24.04.

**Where the hardening ended up (2026-09-20).** After the move to reading `pg_hba` from the server, four
more rounds each found the same class of hole one layer in: a trust for one database, a quoted address,
a role list (`all,bob`), a list named from a file (`@admins`), a list continued after a blank. The fix that
closed the class (change `agree-on-what-a-trust-rule-covers`, then commits on `harden-for-0-2-0`) is a
rule, not a shape: the rule's own line may *confirm* the server's reading — that `all` was quoted — and
may never narrow it. Alongside: the test suite was mutation-audited (37 unnoticed mutations, all guarded
now), the sdist ships what its tests read, and the operator surface has a spec.

**Carrying the migration work forward** (change `carry-the-migration-work-forward`, archived). A
migration is rehearsed several times and run once, and the corrections the rehearsals produce lived in
the environment, which cleaning deletes. Reviewed code is now promoted to a location the operator owns
and taken as given by the next run; what was decided about a module with no successor is recorded,
reused between clients and reported as stale when the sources overtake it; and a migration environment
can name OCA repositories, so that half of coverage is derived instead of filled by hand.

**Seeing what a run did.** A chain of seven steps takes hours and used to leave only seven
Odoo logs. The driver now records each step as it runs it (`logs/steps.tsv`, one appended line per
event); a run can be **followed live** from those marks, and reported on **afterwards and
cumulatively** — every run of the environment, opening with what is still unresolved. The parsing is
the tool's, not an assistant's: `odoo_dwg/runlog.py` is pure and reads three sources it does not write
(the step log, Odoo's own log line, the firewall's journal).

Alongside it, **mail capture stopped being a one-way door** (change `capture-mail-without-losing-it`):
the old redirect overwrote the client's SMTP credentials with no record of them, so it could only be used
on a copy destined for the bin — which is the opposite of what a rehearsed migration produces. Capture now
deactivates and adds, restore gives back exactly what was there, and a read-only check answers whether
mail can leave.

And the rehearsal got an instrument of its own (change `rehearse-with-a-module-that-breaks`): an add-on
generated per chain, carrying one probe per class of change that chain contains, derived from its own
analysis files — so a step can be asked what it took away, and the quiet classes (a field that moved
module, one that stopped being stored) stop being invisible.

Finally, the read-only answers came out from behind the menu (change `answer-without-the-menu`):
`egress check`, `mail check`, `migrate report` and `migrate probes` write nothing and carry their verdict
in an exit code, and the three thin skills — migration triage, the OpenSnitch rule check, Mailpit
configuration — are wrappers over them rather than parsers of their own. The rule audit also answers a
question nothing answered before: whether anything on the host now sorts ahead of the rule confining Odoo.

And the rehearsal stopped needing a client (change `rehearse-on-demo-data`): a source database can be
seeded from Odoo's own demo data, with a module set drawn from what this chain actually does to what is on
disk — one absorbed, one renamed, one that carries on. Module fates are read with renamed and absorbed kept
apart, and joined the tester's probe classes.

**Accepted (2026-09-20):** a 12.0 → 14.0 demo rehearsal ran end to end on the reference host. Odoo 12's
demo data plus four OCA modules chosen for their different fates were seeded, dumped, and migrated through
both layouts (the ≤ 13 fork at 12 → 13, the upgrade-path at 13 → 14), checkpointed at each step. Every fate
happened as the sources declared: `account_coa_menu` and `website_sale_product_style_badge` absorbed into
`account_menu` and `website_sale`, `website_sale_attribute_filter_category` renamed,
`partner_firstname` carried on with its own columns intact. The live watch, the cumulative report and the
read-only checks were exercised against the running chain.

It cost six fixes, all in shipped code and none visible to the suite (see `CHANGELOG.md`) — the reason for
running it.

A second pass added the rehearsal tester: the generated add-on installed on Odoo 12, carried its 25 probe
records through both steps, and reported them afterwards without Odoo running — 7 `gone as predicted`
(including the absorbed `account_coa_menu`), 16 `intact` across every quiet class, and **2 `not observed`**,
which is the honest answer for two module subjects that had never been installed in that database and which
an earlier pass had reported as the chain behaving.

Both followed: a 12 → 19 rehearsal on demo data, and the first client's 12 → 18 migration (see Features below).

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

- ~~Findings ledger and client reports~~ — **done** (2026-09-23, change `record-what-a-migration-finds`).
  Spec 1 of 3 from the first real client intake:
  - one ledger per environment, whose findings carry their evidence, their re-deriving query and the
    client's decision history;
  - a corrections log;
  - client and extended reports rendered from the ledger in a language chosen per report.

  The intake's prototype ledger was converted and renders the same reports, minus what the prototype got
  wrong.
- ~~Neutralise a production copy~~ — **done** (2026-09-23, change `neutralise-a-production-copy`),
  spec 2 of 3.
  - **Reversible catalogue**, recorded inside the database and guarded per version from 12.0 to 18.0.
  - **Re-applied everywhere Odoo can switch crons back on:** by the driver after every step, and by
    `open_for_testing.sh` before every start, which then runs no cron thread.
  - **Restore is manual only.**

  Not done yet:
  - **Official `neutralize.sql` files not covered.** `tools/verify_neutralise_sources.py` lists them:
    mostly provider-specific payment and country EDI rules, since the generic payment rule already takes
    every provider out of production.
  - **The same start guard for workspaces** that open client copies (they run one cron thread today).
  - **Starting Odoo on a neutralised client copy** with the firewall and Mailpit installed, and reading the
    firewall journal. The SQL side was rehearsed on a real client copy: it neutralised, re-applied after a
    simulated module update, and restored every touched table byte for byte.

- ~~Take in a client copy~~ — **done in part** (2026-09-23, change `take-in-a-client-copy`, spec 3a):
  - restore with classified errors;
  - a read-only role without secrets;
  - the archive classified;
  - the core identified (official or OCB, and the exact commit, from blobless histories);
  - the filestore;
  - the source built from that core with the client's add-ons, started guarded.

  The rest was spec 3b, **done** (2026-09-24, change `survey-a-client-copy`):
  - the outbound survey as findings, ranked by the catalogue's declared severities;
  - per-step availability across all OCA repositories, fetched only for the steps with gaps;
  - the custom-code network scan, with its positive control.

  Then, from deciding what to do with modules missing at some step (change `rehearse-module-uninstall`,
  **done** 2026-09-24):
  - an uninstall rehearsed on a throwaway clone of a neutralised copy, with every table compared by exact
    row count and columns, and each difference named (module data, wizard, metadata, recomputed, empty,
    data lost);
  - the read-only role reads where a sequence stands (a wizard's only trace), and never advances it;
  - the ledger refuses a finding key it does not know, instead of dropping it on the next write;
  - read-only commands never prompt for the language.

  And from preparing the first client's 12 → 18 rehearsal (change `carry-the-intake-through-the-chain`):
  - the chain's OCA repositories proposed from the intake's availability table, and read back by later
    actions;
  - the preflight and the driver agree on renamed modules' dependencies, and stale decisions;
  - `data_dir` and a hard-linked filestore for every step of the chain.

  Then the audit of the client's own modules from their data (change `audit-client-modules`):
  per-module use since a date, survival in a migrated database, and prints from an access log.

  Then the chain's core (change `choose-the-chain-core`): the steps from 14.0 run on official Odoo or
  OCB, following the client's core by default. The first client's second rehearsal ran on OCB: the
  modules OCB keeps from auto-installing were gone, and the journal code constraint was added.

  Then bank statement lines imported twice (change `find-bank-lines-imported-twice`): proven from the
  bank's own balances, for a source up to 13.0, with a guarded SQL for the first step's pre hook.
  The same step lists closed periods' unreconciled lines, optionally left behind on the accountant's
  decision (change `leave-locked-bank-lines-behind`). And journal codes the target refuses are renamed
  before the chain (change `rename-duplicate-journal-codes`); any journal may also get a readable code
  from the operator (change `rename-any-journal-code`). The second rehearsal found that OpenUpgrade
  14.0 leaves statement lines stored as reconciled, and the driver now repairs them after that step
  (change `repair-statement-line-reconciled-flag`). The upstream fix, a flush in OpenUpgrade, is
  proposed as a draft in OCA/OpenUpgrade#6005. The same repair carries the SII certificate file the
  OCA 14.0 migration of `l10n_es_aeat_sii_oca` leaves in the old table (change
  `carry-the-sii-certificate-file`).

  Then every check the first client's migration needed by hand became one read-only command, `migrate
  audit`, with a thin skill over it (change `audit-migration-coherence`). It covers journal codes, the
  bank-line problems of sources up to 13.0, declared constraints PostgreSQL does not have, required fields
  left empty and stale reconciled flags, on a source copy, a checkpoint or the migrated database.

  Then the client's own modules under new names (change `carry-client-modules`): renamed, merged,
  replaced or dropped as decided, in a stage after the target step with its own checkpoint, repeatable
  alone while porting; `migrate modules` shows the plan and `migrate decide` records a decision from the
  command line.

  Then grouped invoice items (change `ungroup-migrated-invoice-lines`): a 12.0 source's invoices posted
  with grouped journal items show, from OpenUpgrade 16.0 on, an extra line with the whole amount and
  real lines at zero. The target step now moves each amount back to its lines, one move, account and set
  of taxes at a time, and commits only when balances per account, partner and tax and every link are
  unchanged. On the first client's database every filed VAT return and EC sales list recalculated
  identical before and after, and the invoice analysis by product matched the source.

  Then the taxes OpenUpgrade 13.0 adds to reused journal items (change
  `restore-source-move-line-taxes`): the source's journal-item taxes are kept at the source restore, and
  right after the 13.0 step each reused item loses the taxes it did not bear in the source and its
  invoice line did. On the first client's database the affected VAT and withholding returns came back to
  the source's figures.

  Then filed declarations (change `keep-filed-declarations`): OCA's 303 module stopped shipping its 2022
  map in 17.0, and the update deleted every 2022 return's boxes. The driver now keeps the source's boxes,
  links and maps, and puts back at the target what the chain deleted, checking every filed amount.

  Then retiring modules before the chain (change `retire-modules-before-the-chain`): the modules with
  no code at a later step were uninstalled by hand on a prepared copy of the first client's database.
  The driver now does it after the source restore, from `dropped` decisions marked `before-chain`, and
  stops on any data lost that `accepted_losses` does not name. The rehearsal's rules moved to
  `retire.py`, so both judge alike. On the first client's original copy the driver's uninstall named the
  same losses as the rehearsal. Its result matched the hand-prepared copy module by module and column by
  column; the only differing rows were the neutralisation's own record, one login and a test cron that
  only the hand-prepared copy had.

  Not done yet: a client's own module whose manifest declares Odoo S.A. as its author is reported
  "dropped by Odoo; OpenUpgrade removes it". With an intake, where the module loads from is known, and
  that should decide it rather than the author.

- ~~The operator surface has a spec~~ — **done** (2026-09-20, change `name-the-operator-surface`).
  The twelve capabilities all described what the tool does to the *host*; nothing described what the
  operator touches, and "previewed and confirmed" was restated in six of them with no one place
  defining it. Two capabilities were added: `command-plan` (plan → preview → confirm → apply, what a
  step reports, stopping at the first failure, input closed, and that nothing a plan writes is visible
  before it is complete) and `operator-interface` (entry points, the English source language and the
  optional Spanish UI, that generated artifacts are never translated, menus, failure handling, colour).
  Remaining tidy-up, deliberately not done in that change: the six "previewed and confirmed"
  restatements, the three copies of the ready-marker rule and the three of `smtp 127.0.0.1:1025`
  should become references.
- ~~Support matrix~~ — **done** (2026-09-17, change `add-support-matrix`): one authoritative,
  evidence-tiered matrix in `models.py` + [`docs/reference/support-matrix.md`](../reference/support-matrix.md), with
  `tools/verify_support_matrix.py` to re-derive every bound from its official source. Hosts narrowed to
  Ubuntu 22.04/24.04 (BREAKING for Debian); tool Python floor 3.10; per-version Python maxima added
  (derived from each branch's own `requirements.txt` buckets, cross-validated against Odoo 19's declared
  `MAX_PY_VERSION`); Odoo 19's PostgreSQL floor corrected to 13. Interpreter choice now exists in both the
  workspace and migration flows. Development of this repo moved into WSL (clone under `~`, not `/mnt/c`);
  [`docs/host/wsl-setup.md`](../host/wsl-setup.md) covers getting the tool onto a host. `lighten-scope` later narrowed the
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
  [`docs/workspace/editor.md`](../workspace/editor.md) keep the emitted file in step with new releases.
  Validated by running the official OdooLS binaries (1.4.0 stable and 1.5.2 beta) against a generated
  workspace. Open: whether to adopt any 1.5 key once 1.5 reaches the stable channel.
- ~~Provision password-auth mode~~ — **dropped** (2026-09-19, change `lighten-scope`). It serves shared or
  remote PostgreSQL, which a local development tool does not target, and it would add secret generation and
  storage, a plaintext password in `odoo.conf` and new `pg_hba` rules — a security surface with no user.
  Loopback `trust` is documented as intentional in `docs/host/provisioning.md`, with the manual steps if needed.
- ~~Outbound firewall and mail capture~~ — **done** (2026-09-19, change `add-egress-control`). The need was
  testing and migrating copies of production without mailing customers or calling real services. The choice
  was host-level control, since Odoo's `neutralize` is version-bound and blind to custom addons:
  - **OpenSnitch:** deny by default, ask when its window is open, and log every decision to the journal;
  - **Mailpit:** local mail capture.
  
  Both are opt-in in `provision`, pinned and verified, and can be turned off or on, or uninstalled, from its
  menu. A spike and the operator's own test on WSL drove every non-default setting (`proc` monitoring,
  `InterceptUnknown`, fail closed, the journal logger) and the rule order that keeps `odoo-bin` on localhost.
  See [`egress-control.md`](../host/egress-control.md).
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
  any 1.5 key is worth emitting, following [editor integration](../workspace/editor.md).
