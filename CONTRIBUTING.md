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
re-checks an external fact: the support matrix, the editor configuration, the build and start of every Odoo
version, and the pinned firewall and mail-capture releases. Run them when that fact may have moved, and before
a release:

```bash
python tools/verify_support_matrix.py            # re-derive every bound from its official source
python tools/verify_support_matrix.py 18.0 19.0  # only these versions
python tools/verify_odools_config.py             # the editor config vs the latest OdooLS release
python tools/verify_workspace_versions.py        # build every version's venv, start Odoo on each (host)
python tools/verify_egress_pins.py               # OpenSnitch/Mailpit pins vs their signed/published sources
```

All but `verify_workspace_versions.py` only read from the network. That one changes the host: it previews a
plan, asks before applying (or not, with `--yes`), and removes what it created. See
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
