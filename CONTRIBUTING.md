# Contributing

Thanks for your interest. This project is small and spec-driven; the bar is consistency.

## Ground rules

- **Zero runtime dependencies** — Python 3.12+ standard library only. Adding a runtime dependency is an
  architectural decision, not a convenience.
- **Spec-first for non-trivial changes**: behavior lives in `openspec/specs/`; changes go through the
  OpenSpec flow (`openspec/changes/`). Trivial fixes may go straight to a PR.
- **Plan → preview → apply is inviolable**: planners stay pure (building a command is not running it), and
  nothing mutates the host without a previewed, confirmed plan.
- Every Odoo/OpenUpgrade fact must be anchored to official documentation (see `docs/`).
- AI agents working on this repository follow [`CLAUDE.md`](CLAUDE.md).

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
```

| Tool | Needs |
|---|---|
| `verify_support_matrix.py`, `verify_odools_config.py`, `verify_egress_pins.py` | the network |
| `verify_workspace_versions.py` | the network **and** a host it may change (it previews, asks, and cleans up) |
| `verify_generated_shell.py` | `shellcheck` on the host |
| `verify_pg_hba_trust.py` | the host's PostgreSQL binaries; it runs a cluster of its own and takes about a minute |
| `verify_migration_driver.py` | nothing but `bash` |

`verify_migration_driver.py` renders `run_migration.sh` into a temporary directory and executes it with stub `psql`/`pg_dump`/`pg_restore`/`uv`, covering the fresh run,
resume, a gap in the checkpoints, a dump that does not match, a checkpoint that cannot be written, a step
whose OpenUpgrade code is not on disk, a step that fails — which must name itself and its log — and a
12 → 14 chain, so the ≤ 13 layout's own step command and preconditions are executed too, not only the
upgrade-path ones. The unit suite may not shell out, so this is where the *behaviour* of the generated shell is checked — run it
whenever `render_run_migration_sh` changes.

`verify_pg_hba_trust.py` runs the `pg_hba.conf` rewriter over sixteen shapes of that file (the Ubuntu
default; a blanket trust written as CIDR, as `localhost`/`samehost`, indented, in `address netmask` form, as
`hostnossl`, on `all`, on `0.0.0.0/0` and on `127.0.0.0/8`; a file with no `host` rules; one this tool
already narrowed; a role line shadowed by an earlier rule; a `hostssl` and a `hostgssenc` trust; a file with
no trailing newline; and — the only negative case — a password rule whose comment merely mentions trust,
which it must leave alone), asserting each result.

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
