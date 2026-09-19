## Context

Which setuptools a venv gets depends on the interpreter: on Python 3.8 pip resolves 75.x, which still ships
`pkg_resources`, so the `uv` 3.8 venvs worked by luck; on the host's 3.12 it resolves 84.x. `vatnumber==1.2` has
no `pyproject.toml` and is built against the venv's own setuptools (observed: the failing build ran from the venv's
`site-packages`), so pinning the venv's setuptools also fixes the build.

## Decisions

- **One rule, three eras, in `models.py`.** `setuptools_requirement(version)` returns `setuptools<58` (≤ 13),
  `setuptools<81` (14–16) or `setuptools` (≥ 17). It sits next to the other version facts; the planner and the
  template both read it, so `setup_venv.sh` cannot undo what the plan did.
- **`<58` also satisfies `pkg_resources`.** setuptools < 58 still ships it, so ≤ 13 needs one pin, not two.
- **The migration keeps its own mechanism** (installed `<81` plus a 13.0 build-constraints file), validated end to end;
  changing it is out of scope.

- **An unstated maximum is not permission.** `python_in_range` keeps its meaning (only stated bounds count, so
  choosing 3.12 for Odoo 12 is not reported as out of range), but the *default* uses the host only when it is
  no newer than the recommendation. Declaring a derived maximum for 12/13 was rejected: their branches carry no
  interpreter buckets to derive one from, and the support matrix does not invent bounds.

- **Substitute, don't patch, the deprecated `pyldap`.** Its failure is in its own `setup.py`, not in anything
  the tool controls, and pyldap's last release is itself an empty package requiring `python-ldap`. The branch's
  requirements are streamed through `grep -v` into `pip install -r /dev/stdin` together with the replacement, so
  the clone stays untouched and one resolution installs both. Rejected: setting `CC=gcc` (distutils reads the
  interpreter's build-time `CC`, not the environment — tried, still `-R`).

## Risks / Trade-offs

- `python-ldap` 3 is not byte-for-byte `pyldap` 2.4; only Odoo 12's optional `auth_ldap` imports it. → Import
  checked; an LDAP login against a real directory is not exercised.
- A requirement of Odoo ≤ 13 that needs setuptools ≥ 58 to build would now fail. → Checked by building every
  version's venv from 12 to 19 on the reference host and starting Odoo on each.
