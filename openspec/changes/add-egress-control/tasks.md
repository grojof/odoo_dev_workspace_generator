# Tasks

## 1. Pinned facts and templates

- [x] 1.1 Declare the pinned OpenSnitch 1.8.0 packages (URL, SHA-512 and signing key) and Mailpit (version, URL
      and SHA-256) in `odoo_dwg/egress.py`, citing where each value comes from
- [x] 1.2 Render the hardened daemon settings, the `00-odwg-*` baseline rules (resolvers taken as input) and the
      Mailpit systemd unit. Unit tests cover:
      - the rule order, with owned rules ahead of package, operator and UI rules;
      - the Odoo-before-infrastructure invariant;
      - that the host regexp matches no look-alike;
      - that no rule names an assistant.

## 2. Provisioning

- [x] 2.1 Plans:
      - install OpenSnitch without starting it (`policy-rc.d`, guarded), apply the hardened settings to the
        shipped config, write the `00-odwg-*` rules (replacing only those), then start;
      - install Mailpit and enable its unit;
      - abort on any checksum mismatch.
- [x] 2.2 `provision apply` offers both as opt-in steps. `provision check` reports them and flags softened
      settings.
- [x] 2.3 A `provision` submenu to turn each component off or on (persistent) and to uninstall it. Uninstall
      needs a phrase, shows `apt`'s removal list, and keeps the operator's rules.

## 3. Mail capture in Odoo

- [x] 3.1 Add `smtp_server`/`smtp_port` to workspace and migration step configs
- [x] 3.2 Add the "Redirect a database's mail to Mailpit" action to workspace management and to the migration
      menu. It is column-aware for 12–19, needs a confirmation phrase, and database names are validated with
      Odoo's own `DBNAME_PATTERN`.

## 4. Documentation and translation

- [x] 4.1 `docs/egress-control.md`, covering:
      - concepts;
      - starting, reopening and closing the UI (Start menu, command);
      - reading events and the permanent journal record;
      - allowing by destination rather than by process;
      - deleting a rule, and letting Odoo reach one service;
      - turning off and uninstalling, and crash recovery;
      - live-migration guidance;
      - the update procedure. `tools/verify_egress_pins.py` re-checks the pins, the signature and the signing
        key.
- [x] 4.2 Update `docs/provisioning.md`, `docs/commands.md`, `docs/migration.md`, README, CHANGELOG, CLAUDE.md and
      CONTRIBUTING, and add Spanish entries for every new UI string. The pins live in `egress-control.md`, not
      the support matrix, which covers Odoo, Python and PostgreSQL only.

## 5. Acceptance on the reference host

- [x] 5.1 Project checks green
- [x] 5.2 From the menus, on the spike host, after removing the spike's hand-made setup:
      - **Install and configuration:**
        - provision installed both, with checksums verified and the service started only after configuration;
        - the hardened settings and the `00-odwg-*` rules are in place, and the operator's own rule is untouched;
        - a re-run only reconfigures.
      - **Development flow:** `git`, `gh`, `uv`, `pip` in a workspace venv, and `apt` all work.
      - **Blocking:**
        - unknown hosts are denied with the UI closed;
        - a workspace was generated through the firewall;
        - Odoo is rejected for GitHub (listed as infrastructure) and still rejected after 70 s;
        - a broad operator rule "allow `python3.12` always" does not free Odoo.
      - **Mail:**
        - Odoo's mail lands in Mailpit;
        - the redirect action retargets a production-like mail server, and its mail lands in Mailpit.
      - **Record:** decisions reach the journal with the UI closed.
      - **Failure and recovery:**
        - killing the daemon blocks all traffic until systemd restarts it (≤ 30 s);
        - off, on and uninstall work from the submenu.
