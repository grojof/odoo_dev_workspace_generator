# Close what the rehearsals taught

## Why

Two demo rehearsals — a 12 → 14 and a 12 → 19, both run end to end on the reference host — changed how
several gates behave. The code and the docs moved; three things did not, and each is a way for the tool to
say something that is no longer true:

- **The specs enumerate a closed list of probe verdicts.** `migration-preflight` says a probe is reported as
  "one of" five states. There are seven. The two added for *could not measure* and the two for *not this
  step* are the ones that keep the report honest, and no spec mentions them.
- **The skills describe a tool that no longer exists.** None of the three knows the new verdicts, the
  decisions file the driver now reads, the demo seed, module fates, or the dependency check. A thin wrapper
  that explains the wrong output is worse than none: it reads authoritative and is stale.
- **`decisions.json` is documented nowhere.** The driver refuses a run on its strength and the preflight
  honours it, and no page says where it lives or what it holds.

## What changes

Specs, docs and skills are brought level with what the two rehearsals established. No behaviour changes.

- `migration-preflight` records the whole verdict vocabulary and the rule under it: **a probe can only
  report a loss if there was something to lose**, and it is judged against **its own step**.
- `migration-preflight` records that a module's **dependencies** must resolve, not only the module.
- `migration-run` records that the driver honours recorded decisions, that each step judges the database
  **as it is then**, and that a step's log is read **for the run that wrote it**.
- The three skills are rewritten against the current output, and `docs/commands.md` gains the live watch it
  was missing.
- `docs/migration.md` documents `decisions.json`: where it lives, what it holds, and that a decision is
  never believed over the sources.

## Impact

- Affected specs: `migration-preflight`, `migration-run`
- Affected code: none
- Docs: `docs/migration.md`, `docs/commands.md`, `.claude/skills/*/SKILL.md`
