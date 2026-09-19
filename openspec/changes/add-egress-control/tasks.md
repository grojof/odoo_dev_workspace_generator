# Tasks

## 1. Pinned facts and templates

- [ ] 1.1 Declare the pinned OpenSnitch 1.8.0 packages (URL and SHA-512) and Mailpit (version, URL and SHA-256)
      next to the wkhtmltopdf pins, citing where each value comes from
- [ ] 1.2 Render the hardened daemon settings, the `odwg-*` baseline rules (resolvers taken as input), and the
      Mailpit systemd unit; unit tests for rule order, the Odoo-before-infrastructure invariant, and that no
      rule names an assistant

## 2. Provisioning

- [ ] 2.1 Plans: install OpenSnitch without starting it (`policy-rc.d`), apply the hardened settings to the
      shipped config, write the `odwg-*` rules (replacing only those), then start. Install Mailpit and enable
      its unit. Abort on any checksum mismatch.
- [ ] 2.2 `provision apply` offers both as opt-in steps. `provision check` reports them and flags softened
      settings.

## 3. Mail capture in Odoo

- [ ] 3.1 Add `smtp_server`/`smtp_port` to workspace and migration step configs
- [ ] 3.2 Add the "Redirect a database's mail to Mailpit" action, column-aware for 12–19, behind a confirmation
      phrase, to workspace management and to the migration menu

## 4. Documentation and translation

- [ ] 4.1 `docs/egress-control.md`: concepts; starting, reopening and closing the UI (Start menu, command);
      reading events; allowing by destination rather than process; deleting a rule; making history persistent;
      pausing and resuming; recovering after a crash; live-migration guidance; the update procedure with
      signature re-verification
- [ ] 4.2 Update `docs/provisioning.md`, `docs/commands.md`, `docs/migration.md`, `docs/support-matrix.md`,
      README, CHANGELOG and roadmap; add Spanish entries for every new UI string

## 5. Acceptance on the reference host

- [ ] 5.1 Project checks green
- [ ] 5.2 Provision both from the menu on the spike host, which replaces the spike's hand-made configuration,
      and confirm each of the following:
      - the hardened settings and the `odwg-*` rules are in place, and the operator's rules are untouched;
      - the development flow works;
      - an unknown destination is denied with the UI closed;
      - Odoo is blocked after running for more than a minute;
      - Odoo's mail lands in Mailpit;
      - the redirect action retargets a production-like mail server;
      - killing the daemon blocks traffic, and a restart recovers it
