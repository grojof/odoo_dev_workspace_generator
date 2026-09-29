# Proposal

## Why

A module with no code at one step of the chain has to leave before the chain: Odoo skips a module it cannot
load, and the step then runs without it. `dropped` with `"when": "before-chain"` does that. But some of
these modules exist again at the target, and the client uses them: a check that refuses to post an invoice
without a VAT number, or a line without a tax. Retired as `dropped`, the check is simply gone at the target,
and nothing in the plan says so.

The standard advice for such a module is to uninstall it before the migration and install it again in the
new version. The decisions file cannot say that today: `when` is refused on anything but `dropped`, and a
`replaced` decision may not name the module itself.

## What Changes

- **A `replaced` decision may retire the module before the chain.** It takes `"when": "before-chain"`
  (`migrate decide MODULE --decision replaced --to … --before-chain`), and the driver uninstalls it after
  the source restore, with the same checks as a `dropped` one.
- **Its `to` may name the module itself** when it leaves before the chain: it is installed again at the
  target. Anywhere else, naming itself stays refused.
- **The client-modules stage installs the replacements** of a `replaced` module retired before the chain,
  as it does for any `replaced` module, and has nothing left to uninstall for it.

Out of scope: settings the module stored in its own columns. The retirement's comparison already names any
value it would lose, and stops the run unless it is accepted; a module whose settings live in core fields
keeps them.

## Capabilities

### Modified Capabilities

- `migration-preflight`: `when: before-chain` on `replaced` too; `to` may name the module itself then.
- `migration-run`: the retirement after the source restore takes `replaced` decisions; the modules stage
  installs their replacements.

## Impact

`odoo_dwg/carry.py`, `odoo_dwg/workflows/decide.py`, `odoo_dwg/cli.py`, `odoo_dwg/models.py` (a comment),
`odoo_dwg/i18n.py`; tests in `tests/test_carry.py`; docs.
