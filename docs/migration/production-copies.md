---
type: how-to
title: "Working on a copy of production"
description: "Neutralise a copy of production, keep a migration from reaching the outside, open it for testing, and give production its settings back."
tags: [migration, neutralisation, production-copy]
audience: [developer]
updated: 2026-09-25
---

# Working on a copy of production

A copy of production can mail customers, call real services and empty mailboxes. These are the tool's
guards, from the copy's arrival to the cutover. The host-level firewall and mail capture are in
[Egress control and mail capture](../host/egress-control.md).

## Neutralising a copy of production

Mail is one way a copy of production reaches the outside. A copy is armed in several more ways:
- **every cron fires at once**, because their `nextcall` is past by the time the dump arrives;
- **a tax integration in production mode** is one click from submitting real invoices;
- **its IAP tokens and `database.uuid`** tell Odoo's services it is production;
- **its links** point at the production server.

**Neutralise a database**, in the Workspace and Migration menus (phrase `NEUTRALISE`), turns all of that
off. It captures the mail through the action above and applies a catalogue of rules:

| Area | What changes |
|---|---|
| Crons | Every cron is switched off except `base.autovacuum_job` and `queue_job`'s done-job autovacuum, matched by external identifier |
| Queued jobs | Pending jobs are held, so no runner executes them |
| Tax and EDI | The Spanish SII (Odoo's, and OCA's `l10n_es_aeat_sii` / `l10n_es_aeat_sii_oca`), TicketBAI and the EDI proxy go to test mode |
| Payment | Providers or acquirers leave production |
| Delivery | Carriers leave production |
| Accounts and calendars | OAuth providers are disabled; Google and Microsoft calendar synchronisation stops |
| Webhooks | Webhook server actions are disabled |
| IAP | Accounts are disabled |
| Identity | `web.base.url` points at the local instance and is unfrozen, the copy gets its own `database.uuid`, and `database.is_neutralized` is set, so 16.0+ shows its banner |

Each rule acts only where its table and columns exist, so one catalogue serves 12.0 to 18.0. Each rule
cites its source: Odoo's own `data/neutralize.sql` (16.0–19.0) or the OCA file it reads.
`python tools/verify_neutralise_sources.py` re-derives those citations, and lists every official
`neutralize.sql` the catalogue does not cover yet.

The differences from Odoo's own `odoo-bin neutralize` are the point:

| | Odoo's `odoo-bin neutralize` | Neutralise a database |
|---|---|---|
| Available from | 16.0 only | 12.0 to 18.0 |
| Reversible | No: it replaces secrets and deletes push devices | Yes: it deletes nothing, and records every value it changes (row, column, before, after) in a table inside the database, before changing it |
| Survives dump, restore and each migration step | — | Yes, the record does |

**It does not last on its own.** Updating a module rewrites every cron its data does not mark `noupdate`,
active flag included. Installing or reinstalling a module creates its crons active, and every OpenUpgrade
step does both. Re-applying is safe: it turns off what came back or appeared and records only what is new,
so the value recorded first — production's — is the one a restore gives back. This is why the migration
driver re-applies it after every step, and why migrated databases are opened through
[`open_for_testing.sh`](#opening-a-migrated-database-for-testing).

### Asking whether a copy can act

```bash
odoo-dwg neutralise check --database acme_copy
```

It reports, rule by rule, what can still act on the outside, with the mail verdict under it. It writes
nothing. Exit codes:
- `0`: nothing can act;
- `1`: something can;
- `2`: it could not tell.

A database with no active mail server falls back to its configuration file's `smtp_server`. That is said,
not counted as armed: the tool's own configurations point it at the capture.

### Giving production its settings back

**Give a neutralised database its production settings back** (phrase `RESTORE PRODUCTION`) is the
cutover step, and nothing else ever runs it: no driver step, no start script, no end of a chain. It:
- puts back exactly the first run's recorded values;
- restores the mail capture;
- drops its record.

Some rows are reported and left alone:
- **rows that did not exist in production**, recorded by a later run (typically a cron a migration step
  created). They stay off, and are named before the phrase is asked for, so you decide about each one;
- **rows or columns that no longer exist.**

## Keeping a migration from reaching the outside

Each step's `odoo.conf` sends mail to the local capture (`127.0.0.1:1025`) and runs no cron thread. With
the [outbound firewall](../host/egress-control.md) installed, every `odoo-bin` step is also rejected on any non-local
connection, and each attempt is logged.

**The driver neutralises the working database**
([neutralisation](#neutralising-a-copy-of-production)) at three points:
- after restoring the source dump;
- after every successful step, before that step's checkpoint;
- after restoring a checkpoint to resume.

It then checks that nothing can act, and stops the run if something still can. Every checkpoint, and the
migrated database, is therefore neutralised. Re-applying after each step matters because a step's module
updates switch crons back on by themselves. Each neutralisation is a `neutralised` line in `steps.tsv`.

Generating the environment writes `neutralise.sql` and `neutralise_check.sql` beside the driver. An
environment generated before this has neither: the driver then warns that the database is **not**
neutralised, and regenerating adds them.

**The driver never gives production's settings back.** That is **Give a neutralised database its
production settings back**, run by you, on the day of the cutover
([how](#giving-production-its-settings-back)). Keep the firewall on during the run, and
review what it tried to reach before cutover
([live production migrations](#live-production-migrations)).

## Opening a migrated database for testing

Open a migrated database, or a checkpoint you restored, only through the environment's own script:

```bash
~/odoo-migrations/12-to-18/open_for_testing.sh 18.0 migration_12_to_18
```

On every start it does three things, in order:
1. **Neutralises the database again.** This covers anything an install or update switched back on since
   the last start.
2. **Runs the check.** If anything can still act on the outside, it refuses to start and names what.
3. **Starts that version's Odoo** on `http://127.0.0.1:8069`, with **no cron thread**, loopback only, and
   mail sent to the capture.

With no cron thread, a cron that a module you install during the session creates or reactivates cannot
run before the next start turns it off. There is no option to skip either guard.

## Live production migrations

When the migrated database **goes back to production**:
- **Restore its mail configuration** before cutover, and check it: mail must leave again, through the
  client's own servers. Capture never overwrote them, so there is nothing to retype.
- **Do not** run `neutralize` on it.

Keep OpenSnitch running instead:
- **During the migration** (`odoo-bin` steps), every attempt to reach the outside is rejected and logged.
- **Before cutover,** review what the migration tried to reach:
  `journalctl -t opensnitch --since <start> | grep odoo-bin`.
- **At cutover,** start the migrated database on its production host. That host is not firewalled by this tool.
