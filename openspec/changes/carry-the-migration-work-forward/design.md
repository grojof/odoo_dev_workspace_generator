# Design

## Three artifacts with three lifetimes

The work a migration produces is not one kind of thing, and conflating the three is what makes it
disposable today.

| | Who can answer it | Where it belongs | How long it lives |
|---|---|---|---|
| **Official Odoo modules** | The clones and `apriori`, at the time of asking | Nowhere — derived | Per run |
| **OCA modules** | The same, *if the repositories are in the environment* | Nowhere — derived | Per run |
| **The client's own modules** | Only the operator | A durable directory the operator owns | Across clients' lifetimes |
| **What to do about a module with no successor** | Only the operator | A decisions file the operator owns | Across clients |

The middle rows are the reason for the OCA change: without the repositories, a question that *is* derivable
gets answered by hand, and a hand answer about someone else's code is a guess that ages.

## Why the fates are derived and never frozen

It is tempting to write the answers down — after one 12 → 18, every official and OCA module's fate is known,
and the next client could start from that table. The table would be wrong within months and would not say so.
OCA ports modules continuously: a module with no 18.0 branch today may have one next month, and a frozen
"dead" would keep a client on a workaround they no longer need. Odoo's own renames are already declared by
`apriori.py`, which ships in the checkout the step uses — copying it into this tool would be a second source
of truth for a fact the first source states.

This is the project's existing rule (`CLAUDE.md`: anchor to official sources, declare once, re-verify with a
`tools/verify_*.py`) applied to a new kind of fact. What is recorded instead is only what no source can
state: the operator's decision. And a decision carries the evidence it was made against, so the report can
say *"you decided this module was dead in 18.0; it now resolves"* rather than silently applying it.

## Promote copies, and divergence is reported

Copying rather than moving keeps two properties worth having: the environment remains runnable after a
promotion, and a promotion is not a point of no return — the durable copy can be thrown away and made again.
The cost is that the two can drift, which is why drift is reported rather than prevented. Preventing it would
mean locking the environment's copy, and the environment's copy is exactly where the operator works.

Comparison is by content, per module per version, the way `plan_refresh_files` compares generated files. Not
by mtime: a `cp -a` and a `git checkout` both preserve times that say nothing about content.

## The durable location, and git

One directory per version under a base the operator names. Git is **optional and theirs**: the tool writes
files and, if the directory is a repository, offers to commit on the branch for that version — with *their*
identity, *their* hooks and *their* signing, because it is their history.

That is the opposite of the throwaway repositories staging creates inside each stage directory, which exist
only because `odoo-module-migrate` refuses to run outside one and are deliberately insulated from the
operator's git configuration (`-c user.name=odoo-dwg`, `core.hooksPath=/dev/null`, `--no-gpg-sign`). The two
must not be confused, and the generated report says which is which.

A branch per version in one repository is the recommended shape and the one the documentation shows, because
it makes `git diff 13.0..14.0` the answer to "what did that hop change" and leaves the target version's
branch as the thing handed to the client. The tool does not require it: a plain directory per version works,
and a repository per version works.

## Consuming what is promoted

`plan_stage_module` chains today: the operator's source feeds the first step, each later step consumes the
previous step's output. Consuming promoted code changes only where a step's *input* comes from:

- promoted code exists for this module at this version → that is the input, and the migrator does not run
  for that step;
- it does not → the step derives from the previous one, as now.

So a chain with nothing promoted behaves exactly as it does today, and a chain with every version promoted
runs no migrator at all — it assembles what was proven. The report states, per step, which of the two
happened, because "this step was not derived" is a thing the operator must be able to see.

## What this deliberately does not do

- **It does not port OCA modules.** An unported OCA module is work that belongs upstream, and the tool's job
  ends at saying it is unported and recording what was decided.
- **It does not migrate official modules' code.** There is nothing to migrate: the step uses the target
  version's branch.
- **It does not decide anything.** Every decision is the operator's, recorded with its reason, and re-checked
  against the sources each time it is applied.
