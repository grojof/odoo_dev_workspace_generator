# Proposal

## Why

The Odoo 13 step runs in a container, and it **silently under-migrates**. The official `odoo:13.0` image sets
`addons_path = /mnt/extra-addons` in its `/etc/odoo/odoo.conf`, so the containerised `odoo-bin` — even though
it is the OpenUpgrade fork's own, mounted at `/openupgrade` — loads the *image's* add-ons, not the fork's. In
the ≤ 13 OpenUpgrade layout every migration script lives inside its add-on
(`addons/iap/migrations/13.0.1.0/`), so only the core scripts under `odoo/addons/base/migrations/` ever run.
**Every non-core add-on's migration is skipped.**

Measured on the reference box (2026-09-17) by running the same step both ways against the same Odoo 12
database:

| | Docker step | Native step |
|---|---|---|
| `iap_account.company_id` | still there | renamed to `openupgrade_legacy_13_0_company_id`, as the script intends |
| `iap`'s 13.0 migration | never ran | ran (`rename_columns` + `m2o_to_x2m` into `company_ids`) |
| base version, modules, rows | identical | identical |

The orphan column survived the whole chain: the final Odoo 19 database still has `iap_account.company_id`,
a field Odoo 19's model does not declare (it has `company_ids`). In this demo data `iap_account` has no rows,
so nothing was lost — but the post-migration that moves the data into `company_ids` never runs, so on a
client database with IAP accounts, that company assignment would be lost without a word.

And the fix is available: the same step **runs natively on a `uv`-provided Python 3.8**, which was validated
in the same session. Odoo 13's full requirements install on 3.8 with a single build constraint
(`setuptools<58`, because `vatnumber==1.2` still uses `use_2to3`, which setuptools 58 removed), and the
12 → 13 step then completes cleanly — and correctly, including `iap`.

Odoo 13 is the **only** step that can ever run in Docker: a chain's steps are its target versions, so Odoo 12
is restored and never executed, and any chain starting at 13 begins at step 14. Making step 13 native
therefore removes Docker from this project altogether.

## What Changes

- **Run the Odoo 13 step natively**, in a `uv` virtualenv on Python 3.8 like every other step, using the
  OpenUpgrade fork's own `odoo-bin` with an **explicit `--addons-path` that names the fork's `addons/`** —
  never a default, which is how the container went wrong.
- **Per-version build constraints.** A new `constraints-<ver>.txt` alongside the existing
  `overrides-<ver>.txt`, applied with `uv pip install --build-constraints`, carrying `setuptools<58` for the
  branches whose dependencies still use `use_2to3`. The existing overrides repair *what* is installed; this
  repairs *how* it builds.
- **A ≤ 13 step command shape**, distinct from 14+: migrations live inside the add-ons rather than under an
  `--upgrade-path`, and there is no `openupgrade_framework` module to `--load`.
- **Docker leaves the project.** **BREAKING** for anyone relying on these:
  - `provision check` drops the Docker binary / daemon / fallback-image rows;
  - `provision apply` drops the optional Docker Engine install and the `odoo:13.0` / `odoo:12.0` image pulls;
  - the migration preflight drops its Docker checks, and the driver stops requiring `docker` on the host;
  - the support matrix stops describing any version as Docker-acquired.
  Nothing else in the tool used Docker, so this removes a host prerequisite rather than trading it for
  another.

Out of scope: running Odoo 12 (no chain executes it — it is restored and migrated *away from*), and changing
which versions the chain supports.

## Capabilities

### Modified Capabilities
- `migration-environment`: every chain step is native; the interpreter matrix loses its Docker fallback, and
  a step may carry build constraints as well as requirement overrides.
- `migration-run`: the ≤ 13 step runs the fork's `odoo-bin` from its own virtualenv with an explicit
  add-ons path, so the add-on migration scripts of that layout actually run.
- `migration-preflight`: the chain-scoped checks drop Docker and verify the ≤ 13 step's virtualenv instead.
- `provision-check`: drops the Docker rows.
- `provision-apply`: drops the optional Docker Engine install and image pulls.

The support matrix's data changes too (12 and 13 gain a recommended interpreter instead of a container), but
none of its requirements do — the capability never spoke about acquisition methods.

## Impact

- **Code**: `models.py` (acquisition method and the ≤ 13 add-ons path), `planners.py` (build-constraints file,
  a venv for the 13 step, no image pulls), `templates.py` (the ≤ 13 step shape, the constraints file, the
  driver's host preflight), `preflight.py` and `provisioning.py` (drop Docker facts and rows),
  `workflows/provision.py` (drop the Docker prompts).
- **Docs**: `docs/migration.md` (no Docker; the ≤ 13 shape and why the add-ons path is explicit),
  `docs/provisioning.md`, `docs/support-matrix.md`, `README.md`, `docs/roadmap.md`, `CHANGELOG.md`.
- **Dependencies**: removes Docker as a host prerequisite. `uv` was already required.
- **Verification on the reference host**: regenerate the 12 → 19 environment from scratch and rerun the whole
  chain against the Odoo 12 demo dump, then confirm what the container got wrong is now right —
  `iap_account` ends with `company_ids` and no orphan `company_id`.
- **Known limitation to record**: `uv`'s installable floor is 3.8, so a source database older than 12 would
  still have nowhere to run. That is outside the supported range and stays so.
