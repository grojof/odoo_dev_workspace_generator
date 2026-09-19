## Why

Pressing F5 on a generated Odoo 15 workspace stopped at `ModuleNotFoundError: No module named 'pkg_resources'`.
Odoo ≤ 16 imports `pkg_resources` at startup, and setuptools removed it in 81; the workspace venv step ran
`pip install --upgrade pip wheel setuptools` and so installed setuptools 84. The migration environment had been
fixed for exactly this (`fix-preflight-coverage-classification`), but workspace venvs never got the fix. Testing
the other end showed a second defect of the same kind: an Odoo 13 workspace venv cannot be built at all,
because `vatnumber==1.2` still passes `use_2to3`, which setuptools removed in 58. And building every version
on the reference host showed a third: Odoo 12 and 13 defaulted to the host's Python 3.12, because their
maximum is unstated and an unstated maximum bounded nothing, yet their pinned `gevent` does not build on 3.12
(`CompileError: src/gevent/libev/corecext.pyx`).

## What Changes

- Workspace venvs install a setuptools matched to the Odoo version: `setuptools<58` for Odoo ≤ 13,
  `setuptools<81` for 14–16, and unpinned from 17. The rule is declared once in `models.py`
  (`setuptools_requirement`) and used by both the generation plan and the generated `setup_venv.sh`.
- When a version states no Python maximum, the host `python3` is the default only up to the matrix's
  recommendation; above it the recommendation (`uv`) is the default, and the prompt says the host is unproven
  rather than out of range. The operator can still keep the host.
- Migration environments are unchanged: they already pin `setuptools<81` and carry the 13.0 build pin in their
  constraints file.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `workspace-generation`: a per-instance venv installs the setuptools its Odoo version needs, and an unstated
  Python maximum no longer makes a newer host interpreter the default.

## Impact

- Code: `odoo_dwg/models.py`, `odoo_dwg/planners.py`, `odoo_dwg/templates.py`, `odoo_dwg/prompts.py`.
- Tests: `tests/test_planners.py`, `tests/test_templates.py`, `tests/test_support_matrix.py`,
  `tests/test_prompts.py`.
- Existing workspaces are fixed by regenerating the venv, or by running
  `.venv/odoo<major>/bin/pip install 'setuptools<81'` (≤ 16) once.
