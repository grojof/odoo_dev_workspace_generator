# Design

## Before the chain, in SQL

A journal's code is renamed in the working copy before the first step, by a direct `UPDATE` of
`account_journal.code`. Up to 13.0 an entry's number comes from the journal's `ir.sequence`, whose prefix
the ORM rewrites when the code changes through `write`. A direct update leaves the sequence, and so every
existing and future number, as it was. From 14.0 a new sequence starts from the code, which is the point
of the rename. Applied before the chain, the 15.0 step adds the constraint instead of logging that it
could not.

## Which journal keeps the code

The one with most entries, the lowest id on a tie. The history the client reads, and any export by code,
then keeps working for the journal that has most of it.

## Proposals are a starting point

A generated code is the old one's letters and digits, cut to leave room for a digit, plus the first digit
that makes it unique in the company (`BANK1` → `BANK2`, or the next digit that is free). A meaningful code (bank
and brand) is the operator's to choose. The table is the place to edit it, and the step keeps what the
operator wrote.
