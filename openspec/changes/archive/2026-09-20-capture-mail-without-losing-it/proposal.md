# Capture the mail without losing the way back

## Why

The redirect action overwrites every `ir_mail_server` row of the chosen database: host, port, encryption,
user and password. The credentials it overwrites are the client's, and nothing anywhere records what they
were. It is a one-way door, and its own prompt says so — *"never on a database going back to production"*.

That prohibition is incompatible with why the tool exists. A rehearsed migration ends by running the chain
once, for real, on the client's latest dump; **the database that comes out the far end is the one that goes
into production**. It must not mail customers while it is being migrated and rehearsed, and it must mail
them normally the day it goes live. Today those two requirements cannot both be met: capturing the mail
destroys the configuration that going live needs.

The operator's workaround is to keep the production mail settings somewhere outside the tool and retype
them at the end, from memory or a screenshot, on the day with the least room for a mistake.

## What changes

Capture stops overwriting anything. It **deactivates** the client's mail servers and **adds** one of its
own pointing at Mailpit, so the client's hosts and passwords stay in their own columns, untouched, and the
capture is a visible row an operator can see and test from Odoo's own UI.

The added row is not built column by column — it is **cloned from an existing row**, overriding only what
capture needs. `ir_mail_server` gained required columns between 12.0 and 19.0 (`smtp_authentication` among
them), and a hand-built `INSERT` that misses one fails at the step. Cloning inherits whatever columns that
version has.

- **Capture** deactivates the active mail servers and fetchmail servers, adds the Mailpit server, and
  records which rows it deactivated and which it added, in a table inside that same database, so the record
  survives the seven dump-and-restore hops of a migration chain.
- **Restore** removes the added server, reactivates exactly the rows capture deactivated — not the ones the
  client had already disabled — and drops the record.
- **Check** answers, read-only, the one question worth asking: *can mail leave this database right now?*
  It names every active mail server that is not the capture, says whether fetchmail is running, and whether
  a capture is in effect.
- The confirmation phrase becomes `CAPTURE`, and its prompt no longer has to warn the operator off a
  database going to production, because that is now the supported case.

Capture is idempotent, which a chain requires: it runs again at a later step without switching off the
server it added at an earlier one.

The old one-way rewrite is removed rather than kept beside the new action: leaving both would leave the
destructive one as the default a hurried operator picks.

## Impact

- Affected specs: `mail-capture`
- Affected code: `odoo_dwg/egress.py` (the SQL), `odoo_dwg/planners.py`, `odoo_dwg/workflows/common.py`,
  `odoo_dwg/i18n.py`, `docs/egress-control.md`, `docs/migration.md`, `docs/commands.md`
- No schema of Odoo's is written to: only `active`, a column every version has, plus one table of the
  tool's own that restore removes.
