# Design

**Read the repositories back from disk instead of recording them.** The step directories already are the
record. They are what the step configurations point at, and what the driver was generated with. A second
record could disagree with them.

**Propose from the availability table.** The table is the intake's answer to "where is each module at each
step". Proposing from it keeps the operator in charge of the list, and they may drop a repository whose
only module will be uninstalled. It also means the one fact the first rehearsal needed is no longer missed.

**Hard links for the working database, after every restore.** This is the same reasoning as
`open_for_testing.sh`: no space is used, and Odoo never rewrites an attachment in place. The function is
called after each `createdb`, so a resume from a checkpoint has files too. Without an intake the function is
empty, and the rendered driver says so.

**Stale means "no longer needed anywhere".** A decision records a module and a chain, not a step. Making it
per step would change a file operators carry between clients. What was wrong was the verdict, so the verdict
changes.
