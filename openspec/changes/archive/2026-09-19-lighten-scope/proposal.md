# Proposal

## Why

A review of the remaining backlog (2026-09-19) asked of every item whether it adds value or only adds
maintenance. The answers, with the measurements behind them:

- **Workspace clones are far heavier than the backlog assumed.** Its note said a single-branch Odoo clone is
  "~394 MB"; measured on the reference box, `odoo-14.0` is 4.2 GB and `odoo-18.0` 5.7 GB, almost all of it
  history (3.4 GB and 4.7 GB of `.git`, 145k and 190k commits). The same clones at `--depth 1`, which the
  migration surface already uses, are 0.9 GB and 1.3 GB. Development in a workspace never reads that history,
  and anyone who wants it can fetch it in one command.
- **Ubuntu 22.04 is declared supported but was never run.** That is the exact situation Debian was dropped
  for: claiming support nobody tested. Keeping it also pins the tool's own Python floor at 3.10, which is the
  only reason a separate 3.10 test run exists and why tests have to work around `tomllib` (3.11+).
- **PostgreSQL password authentication** targets shared or remote servers, which this local development tool
  does not serve; it would add secret generation and storage, a plaintext password in `odoo.conf`, and new
  `pg_hba` rules — a security surface with no user.
- **AI emitters** would couple the tool to assistant-specific formats (`CLAUDE.md`, skills, other assistants'
  rules files) that change month to month, while the per-workspace README already gives any assistant its
  context without coupling to one.

## What Changes

- **Workspace clones are shallow by default** (`git clone --depth 1 --branch <v> --single-branch`), with no new
  profile option. Existing clones are not touched. `git -C <clone> fetch --unshallow` restores history for
  whoever needs `log`/`blame`, and it is documented. Refreshing a shallow clone keeps working (`pull --ff-only`
  was verified to advance it).
- **Ubuntu 24.04 is the only supported host.** **BREAKING** for Ubuntu 22.04: `provision check` reports it as
  unsupported and `provision apply` refuses it, like any other host outside the matrix. The tool's Python floor
  rises to **3.12** (24.04's system Python): `requires-python`, the ruff target, and the matrix change together;
  the separate 3.10 test run goes away, and `tomllib` is used directly. Package assets kept only for hosts that
  are no longer accepted are removed.
- **Two backlog items are dropped, with the reason recorded** so they are not reopened without one: PostgreSQL
  password authentication (loopback `trust` stays, documented as intentional for local development, with how
  to change it by hand) and AI emitters (the parked `add-ai-emitters` proposal is deleted and the principle in
  `CLAUDE.md` no longer promises them).
- **Two validation items become one manual check**: the generated `launch.json` attaching with debugpy and the
  official extension's status-bar profile switcher are both "open the workspace in VSCode once", not tracked
  work.

Out of scope: changing which Odoo versions are supported, and anything about the migration surface's clones
(already shallow).

## Capabilities

### Modified Capabilities
- `workspace-generation`: the shared repository cache clones each Odoo version shallowly.

The support matrix's data changes (one host, a 3.12 floor), but none of its requirements do: they speak of "the
host releases the matrix declares" and "the minimum Python the tool itself runs on", not of specific values.

## Impact

- **Code**: `planners.py` (clone command, wkhtmltopdf assets), `models.py` (supported hosts, tool floor),
  `pyproject.toml` (`requires-python`, classifiers, ruff target).
- **Tests**: the host-release and tool-floor tests, and the TOML tests that no longer need `importorskip`.
- **Docs**: `docs/support-matrix.md`, `README.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `docs/wsl-setup.md`,
  `docs/provisioning.md`, `docs/workspace-layout.md`, `docs/roadmap.md`, `CHANGELOG.md`.
- **Removed**: `openspec/changes/add-ai-emitters/`.
- **Verifiable on the reference host**: generate a workspace from an empty cache and confirm the clone is
  shallow, sized as measured above, that the refresh action advances it, and that the full suite passes on
  3.12 with the raised floor.
