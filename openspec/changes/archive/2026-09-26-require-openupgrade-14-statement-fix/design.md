# Design

## The precondition

The marker is the line the fix adds, `env["account.bank.statement.line"].flush()`, searched with a fixed
string in the checkout's `openupgrade_scripts/scripts/account/14.0.1.1/post-migration.py`. Commit ancestry
cannot be checked: the tool clones one commit deep. When a later upstream edit moves or rewrites the line,
the check fails loudly and names the file, and the marker is updated. That is better than trusting a
checkout silently.

It runs with the step's other preconditions, before any change to the database, only for a source up to
13.0: from 14.0 on every line already has its entry, and the defect cannot occur.

## The check

`STALE_RECONCILED_LINES_FROM` stays the one selection, shared with `migrate audit`. After the step and its
post hook, `psql` counts it. Zero records `check statement-lines-is-reconciled` in the step record; more
stops the step before its checkpoint, with the count.
