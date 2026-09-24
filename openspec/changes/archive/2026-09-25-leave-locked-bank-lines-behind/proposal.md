# Proposal

## Why

Up to 13.0 an unreconciled bank statement line has no entry, and OpenUpgrade's 14.0 step gives every one
an entry. For lines in periods the client has closed and filed, that posts entries dated in those periods.
It is also where most of the 14.0 step's time goes: on the first client's copy it created entries at
about 6 lines a second. Whether those lines go to the new version is an accounting decision. Where the
client's accountant decides they should not, the migration needs a safe way to leave them behind, with
the lines delivered in a file. Some of them may be real collections or payments never registered, and
those must stay.

## What Changes

The bank step (**Find bank statement lines imported twice**) also records the unreconciled lines dated on
or before their company's lock date, other than the certain duplicates:

- those whose exact amount matches an open receivable or payable item of the same partner are **kept**:
  they may be collections or payments never registered;
- the rest are listed in full (journal, date, amount, label, reference, partner, note, statement), as the
  file to deliver;
- a second guarded SQL file removes them from a working copy only while they still have no journal item and
  are still on or before the lock date. It is optional: the operator puts it in the first step's pre hook
  only when the client's accountant chose this.

## Capabilities

### Modified Capabilities

- `client-intake`: unreconciled lines of closed periods, optionally left behind.

## Impact

- `odoo_dwg/intake.py`, `odoo_dwg/workflows/intake.py`, tests, `tools/verify_intake.py`, docs.
