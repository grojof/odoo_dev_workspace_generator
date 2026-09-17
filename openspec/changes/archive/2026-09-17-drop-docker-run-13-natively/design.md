# Design

## Context

See `proposal.md` — Why. The measurements that decide this design, all from the reference box (2026-09-17):

- The `odoo:13.0` image's `/etc/odoo/odoo.conf` sets `addons_path = /mnt/extra-addons`, and `ODOO_RC` points
  at it. The container therefore ran the fork's `odoo-bin` against the *image's* add-ons.
- OpenUpgrade 13.0 keeps migration scripts inside add-ons (`addons/iap/migrations/13.0.1.0/`) and in the core
  package (`odoo/addons/base/migrations/13.0.1.3/`). Only the latter is reachable without an add-ons path, so
  only core migrations ran.
- Odoo 13's full `requirements.txt` installs on a `uv` Python 3.8 with one build constraint
  (`setuptools<58`); the 12 → 13 step then completes with exit 0 and produces the same database as the
  container **plus** the `iap` migration the container skipped.
- `uv` provides 3.8 through 3.15 on this host, so the interpreter for the 13 step is available the same way
  as every other step's.

## Goals / Non-Goals

**Goals:**

- One execution model for every step: a `uv` virtualenv and the branch's own `odoo-bin`.
- Make the add-ons path an explicit, stated input everywhere, since leaving it implicit is the defect.
- Remove Docker from the project rather than move the dependency somewhere else.

**Non-Goals:**

- Running Odoo 12. No chain executes it; it is the database's starting point, not a step.
- Supporting sources older than 12. `uv`'s floor is 3.8 and those branches need 3.5/3.6, so they would need
  the very container path this change removes. Out of the supported range, and staying there.
- Reproducing the container's environment (its OS libraries, its wkhtmltopdf). The host provisioning already
  supplies what Odoo needs to build and run.

## Decisions

### D1: The ≤ 13 step gets its own command shape, with the add-ons path spelled out

Rather than teach one renderer to bend, emit two shapes: ≥ 14 keeps `--upgrade-path` +
`--load=base,web,openupgrade_framework`; ≤ 13 runs the fork's `odoo-bin` with
`--addons-path=<custom>,<oca>,<fork>/addons` and neither flag. The path is always explicit, never inherited
from a config file or a default, because the entire bug was an inherited path that looked fine.

*Alternative considered:* keep the container and pass `--addons-path` into it. Rejected as the primary fix:
it repairs this instance of the problem while leaving the tool dependent on an image whose configuration it
does not control, and whose Python (3.6) it cannot otherwise use.

### D2: Build constraints are a separate file from overrides

`overrides-<ver>.txt` changes *what* resolves; `constraints-<ver>.txt` with `--build-constraints` changes what
the *build* environment may use. They solve different failures (`gevent` pins that do not resolve versus
`vatnumber` that cannot build), and conflating them would hide which repair a step actually needs. Only
branches that need one get one.

### D3: `setuptools<58` is scoped to 13.0, not applied broadly

The `use_2to3` removal only bites the 13.0 branch's dependency set here. Applying an old setuptools to every
build would slow and weaken every other step for no reason. If another branch turns out to need it, it joins
the same table — the mechanism is per version by construction.

Note this coexists with the *runtime* pin `setuptools<81` for Odoo ≤ 16: one constrains the build environment,
the other what ends up installed. A step can need both, and 13.0 does.

### D4: Docker leaves, rather than becoming optional-but-unused

Half-removing it — keeping the provisioning options and the readiness rows "in case" — would leave the tool
describing a prerequisite it never uses and operators installing a container runtime for nothing. The rows,
the prompts, the probes and the images all go, and the roadmap records why so a future session does not
"restore" them.

*Risk accepted:* an operator who provisioned Docker because this tool asked now has an unused package. The
removal notes say so.

### D5: The 13 step's config file joins the others

Today no `conf/odoo13.conf` is written, because the container step took its settings as flags. A native step
gets a config like every other, so the add-ons path and database settings live in one visible place. The
config's add-ons path for ≤ 13 lists custom, OCA and the fork's `addons` — not a nonexistent `odoo-13.0`
clone, which is what the generic composition would have produced.

## Risks / Trade-offs

- **Old pins built by a modern toolchain** → the 13.0 requirements built cleanly on this host with the
  documented build dependencies present; `provision apply` installs exactly those. A host missing them fails
  at build with a clear compiler error rather than silently.
- **We lose the container's known-good environment** → that environment was the problem: its add-ons path
  made the step under-migrate. A native step uses the fork's own code for both core and add-ons.
- **`uv` becomes load-bearing for the whole chain** → it already was for every step from 14 up, and it is a
  `provision check` row.
- **Someone still needs Docker for an older source** → out of the supported range; the proposal says so
  rather than leaving a half-path behind.

## Migration Plan

Land the interpreter and venv changes first (the 13 step gains a venv, constraints file and config), then the
step shape in the driver, then strip Docker from preflight, provisioning and their workflows, then the docs.
Verify by regenerating the 12 → 19 environment from scratch and rerunning the whole chain against the Odoo 12
demo dump; the acceptance criterion is the thing the container got wrong — `iap_account` ending with
`company_ids` and no orphan `company_id`.

Operators with an existing environment regenerate it: the 13 step's venv does not exist yet, and the driver
is rewritten anyway.
