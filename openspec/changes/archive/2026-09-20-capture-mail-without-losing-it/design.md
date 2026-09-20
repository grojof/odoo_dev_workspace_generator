# Design

## The fact this rests on

`ir_mail_server.active` exists in every version of the chain, and Odoo picks its outgoing server with
`search([], order='sequence', limit=1)` — an `active`-filtered search — falling back to the configuration
file's `smtp_server` when it finds none. Read, not assumed:

| Version | Source | `active` | Fallback |
|---|---|---|---|
| 12.0 | `odoo/addons/base/models/ir_mail_server.py` | line 148 | line 214 → 228 |
| 13.0 | OpenUpgrade 13.0 fork, same path | line 162 | line 238 → 252 |
| 14.0 | same path | line 104 | line 197 → 211 |
| 19.0 | same path | line 181 | line 418 → 464 |

Two consequences. Deactivating is enough to stop mail leaving through a configured server; and a lower
`sequence` on the added row is what makes Odoo pick the capture rather than anything else.

## Why the added server is cloned, not written

`ir_mail_server`'s required columns are not the same across the chain: 19.0 requires
`smtp_authentication`, which 12.0 does not have. An `INSERT` naming columns has to be right for eight
schemas, and being wrong shows up as a failed migration step, not as a test.

`jsonb_populate_record(NULL::ir_mail_server, to_jsonb(src) || jsonb_build_object(…))` takes the table's own
row type, so every column that version has comes along with a value that already satisfied its
constraints. The overrides are only the fields capture means to change.

When the table has no rows there is nothing to clone — and nothing to capture either: with no mail server
at all, Odoo already falls back to the configuration file, which the generated `odoo.conf` points at
Mailpit. Check reports that state rather than pretending a capture happened.

## Why the record lives in the database

The record of what was deactivated has to survive seven `pg_dump`/`pg_restore` hops, `Clean a migration
environment`, and the months between the rehearsals and the real run. A file in the environment survives
none of those reliably; a table in the database survives all of them, because it *is* the database being
carried forward. `odwg_mail_capture` is inert — no Odoo model refers to it, so nothing loads it — and
restore drops it.

The risk it carries is a table left behind in a production database if restore is never run. That is the
same risk as never running restore at all, which check reports every time it is asked.

## Ordering inside capture

Capture runs as one statement, and the order inside it is load-bearing:

1. record the currently active rows — before anything is deactivated, or there is nothing left to observe;
2. deactivate them, **excluding any row recorded as added** — without that exclusion, a second capture
   switches off the very server keeping the mail in;
3. reactivate the added row if something turned it off;
4. add the capture server only when none is recorded.

Step 2's exclusion was found by running capture twice, not by reading it.

## Alternatives rejected

**Back up the overwritten values and put them back.** Keeps the current rewrite and adds a copy. It
restores *values*, so it is only as good as the copy, and a column the copy did not know about is lost
silently. Deactivating never moves the values at all.

**Keep both actions, the rewrite and the capture.** Two actions doing almost the same thing, one of them
irreversible, and the operator choosing under time pressure. The rewrite goes.
