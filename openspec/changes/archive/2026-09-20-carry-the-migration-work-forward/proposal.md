# Change: Carry the migration work forward

## Why

A real migration is rehearsed several times and run once. The rehearsals are where the work happens: the
module migrator does what it can mechanically, and the operator fixes the rest, version by version, until a
chain of seven steps runs clean. Then the client takes a fresh dump and it all runs again — and that final
run should apply what was already proven, not derive it a second time.

The tool does not support that today.

**The corrections are stored in the most fragile place in the system.** Staging writes each module's per-step
result to `addons/odoo<major>/custom` *inside the migration environment*. That is where the operator's hand
edits live, and it is what `plan_clean_migration` removes with `rm -rf <root>`, what re-staging replaces
behind the `RESTAGE` phrase, and what nothing backs up or versions. Round 12 made the deletion honest — the
confirmation now names the staged modules — but honest deletion of the only copy is still deletion of the
only copy.

**Staging is one-directional.** Step 14 copies from step 13's staged output, so corrections do travel forward
within one environment; that part works. But there is no way to say *"use my reviewed 16.0 code for this
module"*. The only entry point is the operator's source at the chain's start, and everything after it is
re-derived. On the final run that is precisely the wrong behaviour.

**And the work is not all of one kind.** For a given source → target pair, what happens to every *official
Odoo* and *OCA* module is a fact, not a decision: two clients migrating 12 → 18 meet the same answer for
`sale_stock`. Only the client's own modules need per-client work. The preflight's coverage already derives
most of that fact — it resolves each installed module per step and follows the renames and merges
`apriori.py` declares — but two things are missing:

- a migration environment has **no OCA repositories**. `addons/odoo<major>/oca` is created empty for the
  operator to fill by hand, so "is this OCA module ported to 18.0?" cannot be derived, only guessed;
- when a module resolves nowhere and OpenUpgrade does not account for it, the tool reports it and stops
  there. The decision that follows — dropped, replaced by another module, ported by us — is made once and
  then made again for the next client, because nothing records it.

## What Changes

- **Reviewed module code is promoted to a durable location the operator owns**, one directory per version,
  optionally a git repository with a branch per version. Promotion **copies**: the environment stays intact
  and the durable copy is a mirror, not a move.
- **Staging consumes what has been promoted.** For a step whose promoted code exists, that code is the input;
  only the steps with nothing promoted are derived. This is what makes the final run apply proven work.
- **A divergence report.** Once a version is promoted, the environment and the durable copy can drift — the
  operator keeps working in the environment, or edits the durable copy directly. The report says which
  modules differ, per version, so neither copy is silently stale.
- **Decisions about modules with no successor are recorded and reused.** A file the operator owns, keyed by
  module and by source → target pair, saying what was decided and why. The coverage report applies it, and
  says what is still undecided. It is **not** baked into the tool: the fates of Odoo and OCA modules are
  derived from the clones and `apriori` at the time the question is asked, and a decision that no longer
  matches what the sources say is reported as stale rather than believed.
- **A migration environment can name OCA repositories,** cloned per version into the shared cache like the
  workspace surface already does, so the OCA half of coverage is derived instead of assumed.

## Impact

- Affected specs: `migration-staging` (promote, consume, divergence), `migration-preflight` (decisions
  applied to coverage), `migration-environment` (OCA repositories).
- Affected code: `odoo_dwg/models.py` (the durable location, `oca_repos` on `MigrationEnv`),
  `odoo_dwg/planners.py` (promote, consume, OCA clones and links), `odoo_dwg/preflight.py` (decisions),
  `odoo_dwg/workflows/migration.py` (the menu actions), `odoo_dwg/templates.py` (the divergence section of
  the staging report), and their tests.
- Operator-visible: two new migration actions (promote, and a decision prompt when coverage has an
  unanswered module), an OCA field in the migration environment, and a staging report that names divergence.
- Nothing existing changes shape: an environment with nothing promoted and no decisions recorded behaves
  exactly as it does today.
