---
name: migration-triage
description: Triage an OpenUpgrade migration run - what is still open, what each step's log holds, what the firewall refused, and what the rehearsal tester found. Use when asked how a migration went, what went wrong at a step, or what is left to resolve.
license: LGPL-3.0
compatibility: Requires odoo-dwg on PATH (or `python -m odoo_dwg`). The report needs an environment the driver has run in.
metadata:
  author: odoo_dwg
  version: "1.0"
---

Two commands. Both read only; neither writes a file.

```bash
odoo-dwg migrate report --source 12.0 --target 19.0 --lang en
odoo-dwg migrate probes --source 12.0 --target 19.0 --database <db> --lang en
```

Exit **0** nothing open, **1** something to look at, **2** could not tell (no run recorded, or the database
could not be read).

**Do not parse the logs yourself.** `logs/steps.tsv` and each step's Odoo log are already read by the tool,
which counts repeated lines and asks the firewall's journal for each step's own window. Re-reading them by
hand produces a different answer from the one the operator sees, which is worse than no answer.

## The report

It opens with **what is still open** — read that first and lead with it. A step is open when it failed,
never finished, never ran, **or passed while its log holds an error**: a step succeeding and its log being
clean are not the same thing, and this is the case the operator most often misses.

Then, per step: the log summarised by what its lines carry (level, logger, message, count — repeated lines
counted, never repeated), and what the step reached for outside its own machine, refusals first. A refusal
is normal during a migration; an *allow* to something that is not localhost is the one to ask about.

## The probes

`migrate probes` reports what became of each subject the rehearsal tester declared. Two of its verdicts are
findings, and they come first:

- **`gone unannounced`** — the subject is not in the database and nothing predicted it would go. This is a
  quiet loss: the module loaded, the step passed, and a column is empty. Lead with these.
- **`still there`** — the sources said it would go and it did not, so a migration script did not run.

`intact` and `gone as predicted` are the chain behaving. `absent` means the tester never installed — say
that, and do not report the probes as passing.

## A live run

If the operator is asking about a migration that is still going, tell them to use **Menu → Migration →
Follow a running migration** rather than asking you to poll. It shows where the chain is, the running
step's log and what it reached for, and it leaves the driver alone. The report is for afterwards.

## Rules

- **Change nothing, and run nothing that changes anything.** Re-running a step, cleaning an environment,
  capturing mail and promoting modules are all menu actions behind confirmations. Name them.
- **Exit 2 is not a clean run.** Say what could not be read.
- Background: `docs/migration.md`.
