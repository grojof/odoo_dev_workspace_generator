# Design

## Where

Right after the 14.0 step and its post hook, before neutralising and checkpointing. The 15.0 to 18.0 steps
then work on the right value, and a resumed run never repeats the repair on a checkpoint that already has
it (the checkpoint is taken after).

## How

With `odoo-bin shell` on the 14.0 Odoo and venv, which the step just ran. The flag is a stored computed
field whose rule (liquidity, suspense and other lines of the move, and the residual on the suspense line)
lives in Odoo. Re-implementing it in SQL would copy the rule, and the defect already came from a copy. The
shell reads its script from stdin. `--no-http` is set, and the shell starts no cron thread.

## When

Only for a source up to 13.0, where lines without an entry can exist. From 14.0 every line already has its
entry, and the step does not create any.
