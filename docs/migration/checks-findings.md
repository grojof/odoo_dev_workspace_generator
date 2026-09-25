---
type: how-to
title: "Checks and findings"
description: "Ask a database for what breaks a migration, and record what the migration finds with the client's decisions."
audience: [developer]
updated: 2026-09-25
---

# Checks and findings

## Checking a database's coherence: `migrate audit`

A step can succeed and still leave the database wrong. OpenUpgrade logs "unable to add constraint" and
carries on, a required field arrives empty, and a flag is stored stale. Some problems are in the source
before the chain starts. One read-only command asks a database for all of them:

```bash
odoo-dwg migrate audit --database <db> [--db-user <reader>]
```

It writes nothing and changes nothing. It exits 0 when nothing was found, 1 when a check found something,
and 2 when it could not tell. Each check applies by what the database has, not by a version you state. So
run it:
- on the reference before the chain;
- on a restored checkpoint between steps, to see which step broke something;
- on the migrated database.

| Check | Where | Verdict |
|---|---|---|
| Journal codes shared within a company | any | found; codes differing only by case or spaces are information |
| Bank statement lines imported twice | sources up to 13.0 | found, by the intake's proof |
| Unreconciled lines matching a payment posted on the bank account | sources up to 13.0 | found, split by closed and open periods; from 14.0 the bank counts each twice |
| Unreconciled lines of closed periods | sources up to 13.0 | information: carrying them is the accountant's decision |
| Declared unique and check constraints PostgreSQL does not have | any | found; names compared as PostgreSQL truncates them, foreign keys not read |
| Required fields left empty | any | found on active records; archived-only is information; binaries by their attachment |
| Statement lines stored as reconciled with a line still in suspense | from 14.0 | found; the same selection as the 14.0 repair |

Each finding names its fix (an intake step, a data correction on the working copy, the client's
decision) and applies none. Examples carry ids, codes and model names, never partner names or statement
labels. The skill `migration-coherence-check` in `.claude/skills/` tells an assistant when to run it and
how to read it.

## Recording what the migration finds

A client migration finds things long before it runs a step: a tax-reporting module in production mode with
invoices pending, crons that would all fire at start, mail that has not left for years, a core that is OCB
rather than official Odoo. Each finding is recorded once, in the environment's **findings
ledger**, and the reports shown to the client are rendered from that ledger only. A report is never edited
by hand: correct the ledger and render the report again.

```text
~/odoo-migrations/12-to-18/
├── findings/
│   ├── findings.json      # the ledger
│   └── data/*.tsv         # the tables findings cite (first row is the header)
└── reports/
    ├── findings-client.<lang>.md     # for the client
    └── findings-extended.<lang>.md   # everything, and how to check it
```

### What a finding carries

Every finding carries the following, and one without its evidence or its query is refused:

| Field | Holds |
|---|---|
| `id` | A kebab-case id, unique; a withdrawn finding's id is never reused |
| `severity` | `critical`, `high`, `medium`, `low` or `info` |
| `audience` | `client` or `internal`; an internal finding never reaches the client report |
| `evidence` | The structured facts it rests on |
| `query` | The command or SQL that re-derives it |
| `action` | The proposed action |
| `decision` | `pending`, `accepted`, `act` or `declined`, with date and note; earlier decisions stay in `history` |

The query is mandatory because a figure quoted from memory, rather than re-derived, is how a report ends up
telling a client something that is not so.

A finding written for the client also carries a `client` block **per language**: `{"es": {"title", "text",
"question", "level"}}`. A table it attaches is `{"file", "audience", "title", "columns", "note"}`:
- `columns` relabels the header per language;
- `note` is printed under the table.

Values are printed verbatim. If a table goes to a client, write its values the way the client reads them
(`No enviada`, not `not_sent`), in a file of its own per language.

Text meant for a reader is either a plain string or `{"en": …, "es": …}`. This covers phase titles, what
was received, the versions, how the client's data is handled, and the reference links.

### Changing it, and reading it

Everything that writes the ledger or the reports is in **Menu → Migration → Findings and client reports**,
previewed and confirmed:
- start a ledger;
- add findings from a JSON file;
- record a decision;
- set a phase's state;
- withdraw a finding;
- write the reports.

A withdrawn finding moves to the **corrections** log with its reason. It disappears from the findings and
appears in the extended report's corrections, because a report that once showed a false finding must be
able to answer for it.

Reading it writes nothing:

```bash
odoo-dwg migrate findings list     --source 12.0 --target 18.0   # exit 1 while a decision is pending
odoo-dwg migrate findings show ID  --source 12.0 --target 18.0
odoo-dwg migrate findings validate --source 12.0 --target 18.0
odoo-dwg migrate findings report   --source 12.0 --target 18.0 --report-lang es [--kind extended]
odoo-dwg migrate findings links    --source 12.0 --target 18.0
```

`--report-lang` is the report's language and `--lang` the interface's. They are independent: an English
session can render a Spanish client report, byte-for-byte the same as a Spanish session would. A client
finding with no text in the requested language stops the report and is named. It is never replaced by the
technical summary, which is not written for the client.

`links` requests every **reference** link: the context, the client texts, and table titles and notes. It
never requests a URL recorded as evidence, in a summary or in a query. Those are the client's own systems,
and its first version sent a request to a client's production server that way.
