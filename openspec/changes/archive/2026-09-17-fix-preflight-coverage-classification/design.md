# Design

## Context

See `proposal.md` — Why. What the investigation on the reference box established (2026-09-17):

- Every OpenUpgrade branch in the supported range ships `openupgrade_scripts/apriori.py`, declaring
  `renamed_modules` and `merged_modules` (plus model-level dicts this change ignores) as plain literal
  dicts — no imports, no computation.
- The Odoo 12 demo database has 9 installed modules, **all** authored `Odoo S.A.`, including the four the
  current check blocks on. So the author column does separate "Odoo's own code" from everything else for the
  case that matters.
- `preflight.py` already performs I/O (it shells out through `system`), while `planners.py` and
  `templates.py` are pure. The driver is generated text, so anything it needs to read has to be read when it
  runs, not when it is rendered.

## Goals / Non-Goals

**Goals:**

- Stop reporting Odoo's own churn as the operator's problem, without weakening the check where it protects a
  real migration.
- One rule, applied identically by the interactive preflight and by the generated driver.

**Non-Goals:**

- Acting on the warning class. OpenUpgrade uninstalls modules Odoo dropped; this change only stops
  pretending the operator must supply them.
- Model-level renames (`renamed_models` / `merged_models`). Coverage is about whether code exists for a
  step, and models are OpenUpgrade's business during the upgrade itself.
- Verifying that a successor module is *functionally* equivalent. If OpenUpgrade says `web_editor` becomes
  `html_editor`, this change takes it at its word.

## Decisions

### D1: OpenUpgrade's own `apriori.py` is the authority, read per step

Coverage reads the mapping from the step's own `openupgrade-<version>` checkout rather than from a table
maintained here. The mapping changes per version by design — `web_kanban_gauge` merges at 17.0, `web_editor`
is renamed at 19.0 — so a table in this repo would be a second source of truth that goes stale exactly when
Odoo moves, which is the failure this project's support matrix exists to avoid.

Parsing: the file is literal, so `ast.parse` + `ast.literal_eval` of the two assignments reads it without
executing anything. `exec` would also work and is what OpenUpgrade itself does, but parsing keeps an
untrusted-ish file from running as code in the operator's session.

*Alternative considered:* asking OpenUpgrade at runtime by importing `openupgrade_scripts`. Rejected — it
would need that step's venv and its dependencies just to read two dicts.

### D2: One hop, then fall through

A module is covered when it resolves directly, or when its declared successor resolves. Chained mappings
(A→B in one step, B→C in a later one) resolve naturally because each step consults its own file. Within a
single step, a successor that itself resolves nowhere falls through to classification (D3) under the
*successor's* name, so the report names something the operator can act on.

*Alternative considered:* transitive closure inside a step. Rejected as speculative: no branch in the
supported range chains two mappings in one file, and a cycle would need guarding for no benefit.

### D3: Classify by author, with an exact match — not a substring

An unresolved, unmapped module is Odoo's own (warning) or someone else's (blocking), decided by
`ir_module_module.author`.

**The match must be exact.** OCA modules carry `Odoo Community Association (OCA)`, which contains the word
"Odoo": a substring test would classify every unstaged OCA module as Odoo core and wave it through, turning
this check into one that passes when a real migration is about to fail. The rule is therefore an equality
test against a small set of known Odoo spellings (`Odoo S.A.`, `Odoo SA`, `OpenERP SA`, `OpenERP S.A.`),
matched case-insensitively after trimming, and **anything else — including an empty author — is blocking**.

Erring toward blocking is deliberate: a false block is an operator reading a clear message about one module,
while a false pass is a chain that dies mid-upgrade with the database half-migrated.

*Alternative considered:* deciding from whether the module exists in the *source* version's core tree. The
environment does not clone the source version (the chain clones its targets), and for a Docker-backed source
there is nothing on disk to inspect, so the fact is simply not available.

### D4: The rule lives in `preflight.py`; the driver applies it at run time

`preflight.py` gains the reader and the classifier and returns the two classes separately. The driver cannot
be handed the mapping at render time without `templates.py` doing I/O, so it reads `apriori.py` itself when
it runs, through the step's own interpreter, using the same parse. The embedded snippet stays small because
the classification query is SQL: the driver asks PostgreSQL for `(name, author)` and splits the list.

### D5: `gather_coverage` returns classes, not one list

Today it returns `(missing, customs)` where `customs` conflates "in the operator's directory" with "found
nowhere". Return instead, per step, the blocking modules and the warning modules, leaving "genuinely custom,
and present" as its own thing for the adaptation warning that already exists. Callers that render rows get a
state to choose from rather than deriving severity themselves.

## Risks / Trade-offs

- **The author is data, not proof** → a vendor module could claim `Odoo S.A.` and be waved through. Accepted:
  the blast radius is one module reported as a warning instead of a block, the operator still sees it named,
  and the alternative (trusting nothing) is the behaviour being fixed.
- **A branch without `apriori.py`** (or with the file moved) → the reader returns an empty mapping and the
  check degrades to today's behaviour for that step, minus the hard block. The absence is reported, so it
  does not look like "nothing to rename".
- **Warnings become noise** → a 12 → 19 chain warns about a handful of modules per step. They are printed
  once per step with the reason, not repeated per check, and the blocking class stays small and actionable.
- **The driver and the menu drifting apart** → the same fixture-driven tests cover both, and the spec
  requires them to agree.

## Migration Plan

Land the reader and classifier in `preflight.py` with unit tests first (no behaviour change for callers yet),
then switch `gather_coverage`'s return shape and its two callers, then the driver template. Verify by
rerunning the driver that currently refuses, against the Odoo 12 demo dump already on this box — the chain
should reach step 13.0 instead of aborting at the gate.

## Open Questions

- Whether the warning class should be summarised per step ("3 modules Odoo dropped") rather than listed, once
  a long chain shows how noisy it really is. Cosmetic; does not change the specs or the task breakdown.
