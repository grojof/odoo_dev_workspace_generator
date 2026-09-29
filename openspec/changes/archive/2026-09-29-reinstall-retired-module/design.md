# Design

## Context

Retiring before the chain exists for `dropped` decisions (archived change
`2026-09-26-retire-modules-before-the-chain`). The client-modules stage already installs a `replaced`
module's `to` modules and then uninstalls the old one.

## Decisions

- **Reuse `replaced`, not a new kind.** "Replaced by itself, before the chain" says what happens: the module
  leaves, and the module at the target takes its place. A new kind would need its own coverage, audit and
  report wording for the same two operations.
- **`to` naming itself is allowed only with `before-chain`.** Without the retirement, the stage would
  install a module that is already installed and then uninstall it.
- **The plan treats it as both.** It is listed as retired (the driver's retirement uninstalls it), and its
  `to` modules are checked at the target and installed by the stage; it is never uninstalled by the stage,
  since it is no longer installed there.
- **Settings.** Whatever the module kept in its own columns goes with the uninstall. The retirement's
  comparison already names it and stops unless the operator accepted the loss. Settings in core fields (the
  first client's `account.fiscal.position.vat_required`) stay, and the module reads them again at the target.
