# Tasks

## 1. The durable location

- [x] 1.1 `models.py`: where promoted code lives — a base the operator names, one directory per version —
      with the same validation the workspace paths get. It is outside every migration environment, so
      `plan_clean_migration` cannot reach it.
- [x] 1.2 `planners.plan_promote_module(env, module, versions, into)`: copy each version's staged code to
      the durable location. Pure, previewed, and idempotent.
- [x] 1.3 The workflow action: pick the module, pick the versions, phrase-gate a replacement of code already
      promoted, and offer the commit when the destination is a git repository — the operator's identity,
      hooks and signing, unlike the throwaway repositories staging creates.
- [x] 1.4 Tests: the plan copies and never moves; the environment is untouched; a second promotion of the
      same module and version needs the phrase.

## 2. Consuming what is promoted

- [x] 2.1 `plan_stage_module`: take a step's input from the durable location when it holds that module at
      that version, and run no migrator for that step.
- [x] 2.2 The staging report says, per step, *derived* or *from the promoted copy* — a step that was not
      derived is one whose warnings this run will not show.
- [x] 2.3 Tests: nothing promoted behaves as today; everything promoted runs no migrator; a partly promoted
      chain derives only the tail.

## 3. Divergence

- [x] 3.1 Compare the environment's copy and the promoted copy by content, per module and version.
- [x] 3.2 The report names what differs and both paths, and calls neither authoritative.
- [x] 3.3 Tests, including that a copy with identical content and different timestamps is not divergence.

## 4. Decisions

- [ ] 4.1 The file's shape: module, source → target, decision, reason, and the evidence it was made against.
      Hand-editable, and the operator's to carry between clients.
- [ ] 4.2 `preflight`: apply a decision to the module it names; report *undecided* as its own class; report
      a decision the sources have overtaken as **stale** and do not apply it.
- [ ] 4.3 The workflow action that records one, from the coverage table the operator is already reading.
- [ ] 4.4 Tests: applied, undecided, and stale — each against a fixture where the sources changed under the
      decision.

## 5. OCA repositories in a migration environment

- [ ] 5.1 `MigrationEnv.oca_repos`, validated as the workspace surface validates them.
- [ ] 5.2 Generation clones per version into the shared cache and links under `addons/odoo<major>/oca`,
      reusing the workspace planners rather than a second implementation.
- [ ] 5.3 A repository with no branch for a version is reported for that step and does not fail generation.
- [ ] 5.4 Tests, including the report for a version OCA has not ported.

## 6. Prove it end to end

- [ ] 6.1 A `tools/verify_*.py` that runs promote → consume over a throwaway environment with stub module
      code, and asserts the second run derives nothing.
- [ ] 6.2 `docs/migration.md`: the rehearsal-to-final-run cycle, the durable location, the branch-per-version
      shape, and the boundary between the operator's repository and the throwaway ones.
- [ ] 6.3 `CHANGELOG.md`, `docs/roadmap.md`, and `openspec validate --specs`.
