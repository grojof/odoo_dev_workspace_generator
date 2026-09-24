# Tasks

## 1. Pure logic

- [x] 1.1 `Rule.severity` on every catalogue rule, per the table in the spec; verify with a test pinning the
      table and one refusing a rule without it
- [x] 1.2 Survey readers in `intake.py` (overdue crons, queue by channel/state, mail queue by state) and the
      guarded read-only SQL for them; verify with row-reading tests and that the SQL only reads
- [x] 1.3 `module_origin` from the recorded remote and `availability(...)` following fates (renamed, merged,
      moved, MISSING); verify with fixtures for moved, merged and never-ported modules
- [x] 1.4 The network scanner with its positive control; verify each pattern's control, a hit, the refusal
      when a pattern is broken, and that `tests/` and `migrations/` are skipped

## 2. Execution

- [x] 2.1 `system.github_org_repos` (stdlib `urllib`, paginated) and the tree-clone planner with `.absent`
      markers; verify the planner and the pagination parsing in tests, never the network
- [x] 2.2 `tools/verify_intake.py`: availability against throwaway git repositories with a module that moves
      between repositories and one never ported; verify it passes and fails on a mutant

## 3. Surface

- [x] 3.1 Three intake steps (survey, availability, scan), each recording findings and tables; verify with
      workflow tests over stubs
- [x] 3.2 Operator strings in `i18n`; verify the catalog test

## 4. Docs and gates

- [x] 4.1 `docs/migration.md`, `docs/commands.md`, `CHANGELOG.md`, `docs/roadmap.md`; verify every command
      shown
- [x] 4.2 Gates, verifiers, and a grep of the staged tree for any client name, host or real figure

## 5. On the host

- [x] 5.1 Run the three steps on the first client's reference; compare with the hand-made inventory and the
      provisional gaps; record the outcome in its ledger
