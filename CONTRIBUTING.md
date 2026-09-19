# Contributing

Thanks for your interest. This project is small and spec-driven; the bar is consistency.

## Ground rules

- **Zero runtime dependencies** — Python 3.10+ standard library only. Adding a runtime dependency is an
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

The reference box runs Python 3.12, but the [support matrix](docs/support-matrix.md) declares **3.10** as the
floor (Ubuntu 22.04's system Python). Nothing else exercises it, so run the suite on it too — `uv` provides
the interpreter, it costs a fraction of a second, and it is what catches a 3.11+ construct slipping in
(`tomllib`, for instance, does not exist at 3.10):

```bash
PYTHONPATH=. uv run --python 3.10 --with pytest --no-project pytest -q
```

Real end-to-end validation happens on a Linux host (WSL Ubuntu 24.04 is the reference box).

The checks above need no network. One further check does, and is **not** part of the suite — run it when
an Odoo branch may have changed what it supports, or before trusting a bound in the
[support matrix](docs/support-matrix.md):

```bash
python tools/verify_support_matrix.py            # re-derive every bound from its official source
python tools/verify_support_matrix.py 18.0 19.0  # only these versions
python tools/verify_odools_config.py             # the editor config vs the latest OdooLS release
```

It exits non-zero on drift and never edits the declared matrix: fixing drift means editing
`odoo_dwg/models.py` and `docs/support-matrix.md` together. The editor check has its own procedure for
acting on what it reports: [`docs/editor-integration.md`](docs/editor-integration.md). There is no scheduled job running it — make it a
habit before touching the matrix, and every few months otherwise, since a bound drifts when *Odoo* changes,
not when this repository does.

## Commits

Conventional Commits, imperative mood, one logical change per commit. User-facing changes get a line under
`## [Unreleased]` in `CHANGELOG.md`.

## Security

See [SECURITY.md](SECURITY.md) — report vulnerabilities privately, never via public issues.
