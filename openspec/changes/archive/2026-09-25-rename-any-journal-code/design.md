# Design

## Why rename journals with history is safe

Odoo 18 names a new entry after the last entry of the same journal (`sequence.mixin._set_next_sequence`:
same year, else any year). The code is used only when the journal has no entry (`_get_starting_sequence`).
A renamed journal with history therefore keeps numbering with its old prefix, and the rename changes no
existing or future entry number. What does change is anything that selects journals by code, such as an
accountant's export. The step's table is the equivalence to hand over.

## Why refuse a code another journal holds now

The SQL renames one journal at a time, and each rename is guarded by "no journal of the company has the
new code". Swapping or chaining codes (A takes B's code while B takes a new one) would then succeed or
silently do nothing depending on the order. A new code must be free before the file runs.
