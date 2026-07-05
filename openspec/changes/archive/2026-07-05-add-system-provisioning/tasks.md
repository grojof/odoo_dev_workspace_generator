## 1. Host probes (provision-check detection)

- [x] 1.1 Extend `system.py` with probes: `apt_family()` (classify `/etc/os-release` ID/ID_LIKE as debian/ubuntu or unsupported), `package_installed(name)` (`dpkg -s`), `wkhtmltopdf_version()` (+ "with patched qt" flag), `postgres_installed()`/`postgres_running()`/`db_role_exists(role)`, `has_tool("node")`/rtlcss presence.
- [x] 1.2 Add a capability model: a small structure per capability with `detect()` → `(state, detail)` and a pure `plan()` hook. Keep detection (I/O) separate from planning (pure).
- [x] 1.3 Unit-test the check-table logic by injecting probe results (missing → MISSING, un-patched wkhtmltopdf → WARN, non-apt family → unsupported), asserting the rendered rows — no shelling out.

## 2. Provision planners (provision-apply)

- [x] 2.1 `planners.plan_build_deps()` — idempotent `apt-get install` of the Odoo build set validated in F1 (build-essential, pkg-config, python3-dev/venv/pip, libpq/ldap/sasl/ssl/ffi/xml2/xslt/jpeg/zlib/tiff/openjp2/lcms2/webp/harfbuzz/fribidi-dev, fontconfig, postgresql-client).
- [x] 2.2 `planners.plan_postgresql(role)` — install postgresql, `systemctl enable --now`, create the `LOGIN CREATEDB` role via an idempotent `DO $$` guard, and set `127.0.0.1/::1` to `trust` in `pg_hba.conf` (dev convenience, flagged) + reload.
- [x] 2.3 `planners.plan_wkhtmltopdf(major, codename)` — port the sibling's pinned asset table (0.12.6.1-3 SHA-256 per codename) and version rule (0.12.5 ≤14 / 0.12.6 ≥15); download + `sha256sum -c` (abort on mismatch) + install; unmapped codename → recommend distro/skip, never a guessed URL.
- [x] 2.4 `planners.plan_node_rtlcss()` — optional: `apt-get install nodejs npm` + `npm install -g rtlcss`.
- [x] 2.5 Unit-test each planner's command set and the wkhtmltopdf version/asset selection (incl. checksum-abort and unmapped-codename paths). Pure, no execution.

## 3. Workflow wiring (provision-check + provision-apply)

- [x] 3.1 Implement `workflows/provision.py` `check`: run every `detect()`, render the capability table (via `ui.render_table`), change nothing.
- [x] 3.2 Implement `apply`: gate on root (`os.geteuid()==0`, refuse with the sudo message otherwise) and on the apt family (refuse non-Debian/Ubuntu cleanly); compose plans for the missing/selected capabilities (Node/rtlcss opt-in) → `preview_commands` → confirm → `apply_commands`.
- [x] 3.3 Wire the provision menu (Check / Apply) and route errors back to the menu; expose `provision check`/`provision apply` from the CLI subcommand.

## 4. Docs, checks & WSL acceptance

- [x] 4.1 Add `docs/provisioning.md` (frontmatter) — what it installs, the apt-family scope, the dev-trust caveat, and official URLs (Odoo source install, wkhtmltopdf wiki, PostgreSQL role). Update README map + `CHANGELOG.md`.
- [x] 4.2 Run `ruff check .`, `python -m pytest -q`, `openspec validate --specs`, `python -m odoo_dwg provision` smoke; all green.
- [x] 4.3 Acceptance on the WSL box: on the distro, `provision check` reports the current state and `provision apply` reproduces the F1 prerequisite state (build deps + PostgreSQL + role + wkhtmltopdf); record it in `docs/provisioning.md` as the manual acceptance check.
