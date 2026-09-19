## Why

A pre-release audit (two independent reviews, code and docs, verified by hand) found defects that must not
ship in 0.2.0.

**Injection.**
- A migration source/target such as `13.0$(…)` passes validation, because `odoo_major` only looks for a digit
  run. It is then written into `run_migration.sh`, which the operator runs later.
- A workspace profile (`workspace.json`, meant to be shareable) is not validated when a workspace is managed.
  Its versions, name, `db_host` and `oca_repos` (`../..`) reach generated scripts, `odoo.conf` and clone paths.

**The migration driver does not resume as documented.** Checkpoints are written but never restored. After a
failed step, a re-run migrates the half-migrated working database again. A different source dump is also
ignored silently once a checkpoint exists.

**Wrong coverage for the ≤ 13 steps.** Both the interactive preflight and the driver look for core modules
where a legacy (≤ 13) OpenUpgrade fork does not keep them, and for `apriori.py` in the ≥ 14 location.

**The driver's coverage check never blocked.** Its helper is a heredoc, which *is* python's stdin, so the
piped module list arrived empty and no module was ever checked. A chain could start with custom modules
missing — the exact failure that check exists to prevent.

**Checkpoints from another attempt were trusted.** A fresh restore left earlier step dumps in place, so every
step was skipped and the run reported a migration "complete" that had not happened.

**Other defects.**
- A pinned migration interpreter is ignored once a venv is marked ready.
- PostgreSQL probes shell out to `sudo -u postgres`, which prompts mid-flow or reports false MISSING.
- Invalid input crashes the CLI with a traceback.
- **Add a version** mutates the loaded profile before validating or applying.
- An interrupted OpenSnitch install can leave `policy-rc.d` behind, so services no longer start after `apt`.
- The infrastructure rule rejects regional Ubuntu mirrors.
- The firewall's DNS rule allows the resolver's every port, to every process.
- Loopback `trust` covers every role, so any local user can connect as the `postgres` superuser.
- Root downloads land in predictable `/tmp` paths another local user could own.

**And applying a plan prints everything**, so the steps are lost in the output of `git clone` and `pip`.

The docs and specs carry about twenty drifts, and some code is dead or sits in the wrong layer.

## What Changes

- **Validation at every entry point.**
  - Versions must be supported `NN.0` strings.
  - Migration source and target must be chain versions.
  - OCA repository names, `db_host`, ports and the module prefix have validators.
  - Profiles are validated whenever they are loaded, including for management.
  - Generated scripts quote every path with `shlex.quote`.
- **The driver really resumes.**
  - On a re-run it restores the newest checkpoint into the working database before the first pending step.
  - It records the source dump's checksum and refuses a different dump.
- **Legacy coverage.** Coverage sources and `apriori.py` are taken from where each OpenUpgrade layout actually
  keeps them. The driver's coverage check uses the same sources.
- **Migration venvs** record the interpreter they were built with and are rebuilt when it changes.
- **PostgreSQL probes never prompt.**
  - `pg_lsclusters` gives state and version without authenticating.
  - Role checks connect as the role over loopback, or with `sudo -n`.
  - When they cannot tell, they say so instead of reporting MISSING.
- **Robustness.**
  - Workflows report invalid input and file errors instead of crashing.
  - **Add a version** changes nothing until its plan is applied.
  - `policy-rc.d` is removed on any exit, and a leftover one of ours is recognised.
  - The OpenSnitch config is written atomically.
  - The apriori cache does not remember a missing file.
  - wkhtmltopdf says why it is skipped.
  - Staging no longer hides `git` failures.
  - Refresh keeps timestamped backups.
  - The gevent repair recognises `3.10.x`.
- **Structure.**
  - `Command` moves to `models` (pure data), so pure modules no longer import `system`.
  - The mail redirect action and read-only host probes move out of cross-workflow imports.
  - Dead code is removed, including the unused `addon_prefix` profile field.
- **Tests.**
  - Regression tests for every injection vector, the driver's resume logic and legacy coverage.
  - Tests for the interactive workflows: loading, adding a version, refresh interpreters, phrase gating and CLI
    error handling.
- **The driver's coverage check works**: the module list travels in the environment, and an empty list is a
  failure. A fresh run owns its checkpoint directory, a resume drops everything after the first gap, and
  checkpoints and the source hash are written through temp files.
- **Narrower host changes**: loopback `trust` only for the development role, the DNS rule only on port 53,
  and root downloads in a root-only `/var/cache/odoo_dwg`.
- **A plan reports one line per step**, keeping warnings and printing the end of a failed step's output.
  `--verbose` (or `ODWG_VERBOSE=1`) streams everything, as before.
- **Docs and specs.** Every drift both audits listed is fixed, and `SECURITY.md` covers the egress
  components.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `workspace-configuration`: stricter profile validation; `addon_prefix` removed.
- `workspace-management`: profiles validated on load; **Add a version** applies atomically.
- `migration-environment`: source and target validated; interpreter-aware venv readiness.
- `migration-run`: the driver restores the newest checkpoint and binds to one source dump.
- `migration-preflight`: legacy-layout coverage sources and apriori location.
- `provision-check`: PostgreSQL probes never prompt.
- `egress-control`: owned rule prefix wording; regional Ubuntu mirrors.

## Impact

Code across `models`, `planners`, `templates`, `system`, `preflight`, `provisioning`, `egress`, `prompts`,
`cli` and the workflows. New tests. Docs: README, SECURITY, CONTRIBUTING, `docs/*`. Specs as listed. No change
to what a valid profile or migration generates, except quoted paths, `smtp` keys already present, and the
driver's resume block.
