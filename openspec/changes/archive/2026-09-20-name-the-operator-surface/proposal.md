# Change: Name the operator surface

## Why

The twelve capabilities are drawn along one axis — what the tool does to the host — and along that axis they
hold up. The map has no second axis, and two things fall through it.

**The thing the operator touches has no capability.** Nothing in any spec mentions the three entry points and
their sections, `--version`, `--lang` / `ODWG_LANG` / the startup language prompt, the Spanish catalog,
`--verbose` / `ODWG_VERBOSE`, `NO_COLOR` / `FORCE_COLOR`, the `0` cancel contract every menu shares, the file
browser, or that an error a flow cannot use returns to the menu instead of a traceback. `docs/commands.md`
documents all of it as contract and the suite enforces part of it —
`tests/test_i18n.py::test_every_ui_string_has_a_spanish_translation` guards a whole module against a
requirement that does not exist.

**The contract the other capabilities lean on has no capability either.** "Previewed and confirmed" is
restated in six of them (workspace-generation, workspace-management, migration-environment,
migration-staging, provision-apply, mail-capture) without one place saying what a preview shows, what a step
reports, that a failing step stops the plan, or that steps run with their input closed. The same is true of
the interruption-safety machinery built for it — `.odwg-tmp` renames, `.partial` clones, ready markers,
checkpoint temp files — which reads as three independent rules in three capabilities instead of one.

This is how the duplication that produced earlier audit findings got in: a fact restated in six places drifts
in one of them.

## What Changes

- **New capability `command-plan`**: plan → preview → confirm → apply, what applying reports, that the first
  failing step stops the plan, that steps run with input closed, and that every artifact a plan writes
  becomes visible only complete.
- **New capability `operator-interface`**: the entry points and sections, the source language and the
  optional Spanish UI (and that **generated artifacts are never translated**), how menus and prompts behave,
  what happens when something goes wrong, and colour.
- Nothing in the code changes: both capabilities describe behaviour that exists and is tested. The six
  restatements of "previewed and confirmed" are left in place for now — shortening them to a reference is a
  follow-up, and doing it here would mix a map change with a rewrite of six capabilities.

## Impact

- Affected specs: adds `command-plan` and `operator-interface`.
- Affected code: none.
- The capability count goes from 12 to 14, and `openspec validate --specs` covers the CLI and the plan flow
  for the first time.
