# Design

## Default: follow the client

The intake already identifies the client's core, `odoo` or `ocb`, from history (`intake.json`, `core`).
Following it by default keeps the chain on what the client runs, with no question to answer. A patched or
unidentified core has no `core` in the record, so the default is `odoo`, as before.

## Where the choice lives

`MigrationEnv` is rebuilt by every action from the versions the operator types, the OCA repositories read
back from the step directories, and `intake.json`. The chain core follows the same rule. Generation writes
it into every step config's `addons_path` (`.repos/ocb-16.0/addons`), and a later action reads it back from
there. A second record could disagree with the configs the driver actually runs. The configs cannot.

## One path method

`odoo_clone_dir(version)` already names a step's Odoo clone and is used for `addons_path`, `odoo-bin`, the
requirements file, coverage and the clone plan. It now returns `.repos/<chain core>-<version>`. With the
default `odoo`, every path is unchanged, and so are all generated files for an environment without an
intake. The source clone without an intake also goes through it. A seed with a forced `ocb` is then seeded
on OCB, which is consistent: the demo database starts on the core the chain runs.

## Why not the steps up to 13.0

Up to 13.0 the OpenUpgrade branch is itself a full fork of Odoo (`uses_legacy_layout`). There is no
separate core to choose.

## Evidence

- OCB and Odoo differ, from 14.0 to 18.0, mostly in `auto_install` flags. Compared on GitHub
  (`odoo/odoo` `<v>...OCA:<v>`, 2026-09-24): 18.0 turns off 17 modules. 14.0 and 16.0 also carry small code
  changes, and OCA modules that depend on them check for OCB (`purchase_discount` 14.0:
  `hasattr(self.env, "ocb")`).
- OCA tests its modules on both cores (`l10n-spain` and `account-reconcile` 18.0 CI: "test with Odoo",
  "test with OCB"). OpenUpgrade's CI tests on `odoo/odoo` only (`.github/workflows/test.yml`), which is
  why the second rehearsal is part of the change.
