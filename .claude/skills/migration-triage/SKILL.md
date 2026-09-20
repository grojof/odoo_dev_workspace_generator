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

Each step's summary is read **within that step's own window**, so a step re-run after a failure is reported
with what the successful run produced — the log file still holds the earlier attempts.

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

`migrate probes` reports what became of each subject the rehearsal tester declared. **Only two verdicts are
findings**, and they come first:

- **`gone unannounced`** — the subject is not in the database and nothing predicted it would go. This is a
  quiet loss: the module loaded, the step passed, and a column is empty. Lead with these.
- **`still there`** — the sources said it would go and it did not, so a migration script did not run.

Two are the chain behaving: `intact`, and `gone as predicted`.

**Three mean the probe measured nothing**, and they sort last. Never read them as passes, and never report
them as problems either:

- **`not observed`** — the subject was never in this database (a field whose model is not installed, a
  module whose successor is absent too). Nothing to lose, nothing lost.
- **`not yet reached`** — the probe is about a step this database has not reached.
- **`past its step`** — the database is beyond the probe's step, so a missing subject cannot be blamed on
  it; a later step may have removed it.

`absent` means the tester never installed — say that, and do not report the probes as passing.

**Check between steps, not only at the end.** A probe claims something about *its own* step. The driver
leaves a checkpoint per step (`checkpoints/<version>.dump`), so a database at any step can be restored and
asked. Checking a long chain only at the end turns most quiet-class probes into `past its step`.

## When the run was stopped by the preflight

The gate refuses a run for three reasons, and each has a different answer:

- **`<module> missing for <version>`** — nobody supplies that code at that step. Either put it in that
  step's `custom` directory, add the OCA repository that has it, or **record a decision**: the environment's
  `decisions.json` says what was decided about a module with no successor, and both the preflight and the
  driver honour it. An applied decision is always named in the output, never silent.
- **`<module> needs <dep>, which resolves nowhere`** — the module resolves but its manifest names one that
  does not. Adding one OCA repository often requires another.
- **`a module installed since the preflight resolves nowhere`** — a module the chain installed along the
  way, which the source database never had. The run stops at that step; the checkpoints before it stand, so
  fixing it and re-running resumes rather than restarts.

## A live run

If the operator is asking about a migration that is still going, tell them to use **Menu → Migration →
Follow a running migration** rather than asking you to poll. It shows where the chain is, the running
step's log and what it reached for, and it leaves the driver alone. The report is for afterwards.

## Rules

- **Change nothing, and run nothing that changes anything.** Re-running a step, cleaning an environment,
  capturing mail and promoting modules are all menu actions behind confirmations. Name them.
- **Exit 2 is not a clean run.** Say what could not be read.
- Background: `docs/migration.md`.
