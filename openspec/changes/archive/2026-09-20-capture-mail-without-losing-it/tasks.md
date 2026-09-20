# Tasks

## 1. The SQL, and the facts under it

- [x] 1.1 `odoo_dwg/egress.py`: `mail_capture_sql()`, `mail_restore_sql()`, `mail_state_sql(...)`; remove
      `mail_redirect_sql`.
- [x] 1.2 `odoo_dwg/egress.py`: the pure reading of the state rows (`MailServer`, `MailState`, the verdict).
- [x] 1.3 `tools/verify_mail_capture.py`: capture → check → restore against a throwaway PostgreSQL, on a
      12-era and a 19-era `ir_mail_server`, asserting the client's row comes back identical, a deliberately
      disabled server stays disabled, a second capture leaves the capture active, and restore leaves no
      table behind.

## 2. The surface

- [x] 2.1 `odoo_dwg/planners.py`: `plan_mail_capture`, `plan_mail_restore`; remove `plan_mail_redirect`.
- [x] 2.2 `odoo_dwg/system.py`: `psql_rows` for the read-only check.
- [x] 2.3 `odoo_dwg/workflows/common.py`: the three actions, `CAPTURE` phrase, restore's own confirmation.
- [x] 2.4 `odoo_dwg/i18n.py`: the new strings, technical terms left in English.

## 3. Tests

- [x] 3.1 Unit tests for the state reading and the plans; mutation-audit every one of them.

## 4. Documentation

- [x] 4.1 `openspec/specs/mail-capture/spec.md` via the delta; `openspec validate --specs`.
- [x] 4.2 `docs/egress-control.md`, `docs/migration.md`, `docs/commands.md`, `CHANGELOG.md`,
      `docs/roadmap.md`, `CONTRIBUTING.md` (the ninth verifier).
