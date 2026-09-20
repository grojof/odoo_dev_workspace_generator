# Contributing

Thanks for your interest. This project is small and spec-driven; the bar is consistency.

## Ground rules

- **Zero runtime dependencies** — Python 3.12+ standard library only. Adding a runtime dependency is an
  architectural decision, not a convenience.
- **Spec-first for non-trivial changes**: behaviour lives in `openspec/specs/`; a change is a directory
  under `openspec/changes/<name>/` holding `proposal.md` (why and what), `design.md` (the decisions worth
  recording), `tasks.md` (the checklist) and `specs/<capability>/spec.md` (the delta). Implement, keep
  `openspec validate --specs` green, then move the directory to `openspec/changes/archive/<date>-<name>/`
  and fold its delta into the capability's spec. Trivial fixes may go straight to a PR. The archive is also
  where to look for *why* something is the way it is.
- **Plan → preview → apply is inviolable**: planners stay pure (building a command is not running it), and
  nothing mutates the host without a previewed, confirmed plan.
- Every Odoo/OpenUpgrade fact must be anchored to official documentation (see `docs/`).
- AI agents working on this repository follow [`CLAUDE.md`](CLAUDE.md).

## Set up

The package itself has no dependencies; the checks below do.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"             # pytest, ruff
npm install -g @fission-ai/openspec@latest   # the `openspec` CLI (Node)
```

[`docs/wsl-setup.md`](docs/wsl-setup.md) covers getting a host ready from nothing, including a Node that
needs no root.

## Checks before a PR

```bash
python -m pytest -q                 # unit tests (no network, no real filesystem side effects)
python -m ruff check .              # lint
openspec validate --specs           # capability specs well-formed
python -m odoo_dwg --help           # CLI smoke test
```

Real end-to-end validation happens on a Linux host (WSL Ubuntu 24.04 is the reference box).

The checks above need no network and change nothing. The tools below are **not** part of the suite. Each
checks something the suite cannot: an external fact that may have moved (the support matrix, the editor
configuration, the pinned firewall and mail-capture releases), or the behaviour of generated shell on a real
host (the migration driver, every generated script, the `pg_hba.conf` rewriter). Run the first kind when the
fact may have changed, the second when you touch what renders it, and all of them before a release:

```bash
python tools/verify_support_matrix.py            # re-derive every bound from its official source
python tools/verify_support_matrix.py 18.0 19.0  # only these versions
python tools/verify_odools_config.py             # the editor config vs the latest OdooLS release
python tools/verify_workspace_versions.py        # build every version's venv, start Odoo on each
python tools/verify_egress_pins.py               # OpenSnitch/Mailpit pins vs their signed/published sources
python tools/verify_migration_driver.py          # run the generated migration driver against stub binaries
python tools/verify_generated_shell.py           # ShellCheck every generated script
python tools/verify_pg_hba_trust.py              # run the pg_hba rewriter, and ask PostgreSQL about it
python tools/verify_promoted_modules.py         # promote reviewed code, then stage again and derive nothing
python tools/verify_mail_capture.py              # capture, check and restore a database's mail configuration
python tools/verify_migration_tester.py          # generate the rehearsal tester, and run the query it asks
```

| Tool | Needs |
|---|---|
| `verify_support_matrix.py`, `verify_odools_config.py`, `verify_egress_pins.py` | the network |
| `verify_workspace_versions.py` | the network **and** a host it may change (it previews, asks, and cleans up) |
| `verify_generated_shell.py` | `shellcheck` on the host |
| `verify_pg_hba_trust.py`, `verify_mail_capture.py`, `verify_migration_tester.py` | the host's PostgreSQL binaries; each runs a cluster of its own |
| `verify_migration_driver.py` | nothing but `bash` |
| `verify_promoted_modules.py` | nothing but `bash` and `git` |

`verify_migration_tester.py` generates the rehearsal tester from analysis lines copied verbatim out of
OpenUpgrade's files, then asks whether the result is a *module*: every `.py` compiles, the manifest
evaluates to a dict that ships what it declares and sets no `auto_install`, the data file parses with one
record per probe and unique ids, and the access rule is read-only on its own model. It then creates
`ir_model`, `ir_model_fields` and the probe table in a throwaway cluster and runs the real query, so both
findings are produced by PostgreSQL rather than asserted. It also checks that no status in the whole
harvested vocabulary is claimed by two class patterns, and — where the host has the environment's clones —
generates the real chain's tester and checks every probe against a record that states it.

`verify_mail_capture.py` runs capture → check → restore against a cluster of its own, on two
`ir_mail_server` schemas that differ the way Odoo's differ across the chain (a 12-era one, and a 19-era one
where `smtp_authentication` is `NOT NULL`). It asserts what the operator depends on: the client's row comes
back from restore column for column, a server the client had switched off is not switched on, a second
capture leaves the capture's own server active, restore leaves no table behind, and a database that was
never captured is refused. The unit suite asserts the SQL's text; this runs it — which is how a capture
that switched off its own server on the second run, and a boolean read as `t` when PostgreSQL renders it
`true`, were both found.

`verify_promoted_modules.py` runs the promote → consume cycle a rehearsed migration depends on, with a
stub module migrator: the first staging derives every step, a correction made by hand survives
promotion, the second derives **nothing** and lands exactly the reviewed code, the throwaway git
repository does not travel with it, and divergence appears as soon as work continues in the
environment. The unit suite can only assert the plans' text; this executes them.

`verify_migration_driver.py` renders `run_migration.sh` into a temporary directory and executes it with stub `psql`/`pg_dump`/`pg_restore`/`uv`, covering the fresh run,
resume, a gap in the checkpoints, a dump that does not match, a checkpoint that cannot be written, a step
whose OpenUpgrade code is not on disk, a step that fails — which must name itself and its log — and a
12 → 14 chain, so the ≤ 13 layout's own step command and preconditions are executed too, not only the
upgrade-path ones. The unit suite may not shell out, so this is where the *behaviour* of the generated shell is checked — run it
whenever `render_run_migration_sh` changes.

`verify_pg_hba_trust.py` runs the `pg_hba.conf` rewriter over every shape of that file this project has been
caught by, the server's verification step over more, and the check's own answer against whether
`postgres` really connects. The shapes it must narrow: a blanket trust
written as CIDR, as `localhost`/`samehost`, indented, in `address netmask` form, as `hostnossl`, `hostssl` or
`hostgssenc`, on `all`, on `0.0.0.0/0`, on `127.0.0.0/8`, on one database, and with a quoted address. The
shapes it must leave alone: the Ubuntu default, a file with no `host` rules, one this tool already narrowed,
and a password rule whose comment merely mentions trust — a role literally named `all` is covered where
it matters, in the verification step's own cases. And the shapes where
it must insert the role's line rather than read one as reached: a role line shadowed by an earlier rule, the
role's own trust rule on `hostssl`, its own password rule above its trust rule, a shadowing rule that is not
`host all all`, and a file with no trailing newline. The count is deliberately not repeated here — `CASES`
and `AUDIT_CASES` in that file are the list.

It asserts twice over. Once against a reading of the file written independently of the code under test: the
first version of that tool asserted with a copy of `system.py`'s own regex, so every shape both missed
passed as correct — which is how a `hostssl` trust survived three rounds of it. And once against
**PostgreSQL itself**: it creates a throwaway cluster (`initdb` in a temp directory, its own port and
socket, TLS on like the supported host), points it at each fixture, and asks `pg_hba_file_rules` and a real
connection — which it skips, saying so, when those binaries are absent. It never touches the host's own
cluster.

It also runs **the plan's own verification step** against that cluster, over the states only a server knows
about: a rule it cannot parse (so it refused to load the file), a quoted `"all"`, roles named by pattern, a
blanket trust the rewriter left behind, a `hostnossl` rule for the role, and a properly narrowed file.

`verify_generated_shell.py` renders every generated script (both OpenUpgrade layouts, both interpreter
sources) and runs [ShellCheck](https://www.shellcheck.net) on it — install it with
`uv tool install shellcheck-py`, `pipx install shellcheck-py` or `apt install shellcheck`; it is a
development tool, never a dependency of the package. It is the static half and
`verify_migration_driver.py` the behavioural one: ShellCheck does *not* catch a failure masked by `;` in a
function whose last command succeeds, which is exactly the bug that verifier exists for.

`verify_workspace_versions.py` previews a plan, asks before applying (or not, with `--yes`), and removes
what it created. See
[`docs/workspace-layout.md`](docs/workspace-layout.md#re-verifying-every-version) for when to run it.

`verify_support_matrix.py` exits non-zero on drift and never edits the declared matrix: fixing drift means editing
`odoo_dwg/models.py` and `docs/support-matrix.md` together. The editor check has its own procedure for
acting on what it reports: [`docs/editor-integration.md`](docs/editor-integration.md). There is no scheduled job running it — make it a
habit before touching the matrix, and every few months otherwise, since a bound drifts when *Odoo* changes,
not when this repository does.

## Commits

Conventional Commits, imperative mood, one logical change per commit. User-facing changes get a line under
`## [Unreleased]` in `CHANGELOG.md`.

## Security

See [SECURITY.md](SECURITY.md) — report vulnerabilities privately, never via public issues.
