---
name: mailpit-config
description: Check whether a database's mail can still leave the host, and explain how to capture it in Mailpit or give the production configuration back. Use before a rehearsal migration, and before a cutover.
license: LGPL-3.0
compatibility: Requires odoo-dwg on PATH (or `python -m odoo_dwg`) and a reachable PostgreSQL.
metadata:
  author: odoo_dwg
  version: "1.0"
---

Ask the tool, never the database directly:

```bash
odoo-dwg mail check --database <db> --lang en
# --db-host, --db-port, --db-user if the defaults (127.0.0.1 5432 odoo) are wrong
```

Exit **0** mail cannot leave, **1** it can, **2** the database could not be read.

## What it prints

- `Mail can leave <db>.` — an active mail server points somewhere that is not the capture. Every active
  server is listed with its host and port; the capture, if present, is marked.
- `Mail cannot leave <db>.` — the only active server is the capture.
- `<db> has no active mail server` — Odoo will fall back to the `smtp_server` of its configuration file.
  The generated `odoo.conf` points at Mailpit; **another `odoo.conf` may not**, so do not call this
  captured.
- `A capture is in effect: N mail server(s) deactivated, not lost.` — the client's settings are intact in
  their own columns.
- `N fetchmail server(s) are still fetching.` — incoming mail is still being read from a real mailbox.

## The two actions, which you do not perform

Both change a database and both are behind a confirmation phrase in the menu. Name them; never run them.

- **Menu → Migration (or Manage workspace) → Capture a database's mail in Mailpit** (phrase `CAPTURE`).
  Deactivates the client's servers **without altering them** and adds one pointing at `127.0.0.1:1025`.
  Safe to repeat.
- **Menu → … → Restore a database's mail configuration** (phrase `RESTORE`). Removes the added server and
  switches back on exactly what the capture switched off. This is the step before a cutover.

## Rules

- **Before a cutover, the expected answer is `Mail can leave`** — the migrated database is going into
  production and must mail customers. Before a rehearsal it is the opposite. Ask which one this is before
  calling an answer good or bad.
- Captured mail is read at `http://127.0.0.1:8025`.
- Never suggest editing `ir_mail_server` by hand. The capture exists so that nothing has to be retyped.
- Background: `docs/egress-control.md`.

## A migrated database

A rehearsal chain leaves the mail configuration exactly as it found it — capture deactivates and adds, it
never overwrites — so after a 12 → 19 run the client's own servers are still in the database, switched off.
`restore` is what switches them back on, and it is the step before a cutover. Check after restoring: the
expected answer there is **`Mail can leave`**, the opposite of what you want during a rehearsal.
