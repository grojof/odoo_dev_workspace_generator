# Tasks

- [x] 1.1 `repos_from_availability`, and a core module found in OCA later counts as moved; tests
- [x] 1.2 `linked_oca_repos`; `_ask_env` reads them back, and proposes the availability's on generation; test
- [x] 1.3 Preflight dependencies under each step's names; stale only when never needed; tests failing without it
- [x] 1.4 Step configurations name `data_dir` with an intake; the driver's `give_filestore` after every
      restore; tests, the driver verification (hard links, once) and ShellCheck over the intake variant
- [x] 1.5 `pip_requirements`; `step_python_requirements` per step under its names; `plan_step_python_deps`
      held to the venv; the driver's `python_deps_step`; tests, and the helper run on a real interpreter
- [ ] 2.1 Regenerate the first client's chain with the tool, preflight it from the menu, and rehearse
- [x] 2.2 Docs: `docs/migration.md`, `CHANGELOG.md`, `docs/roadmap.md`
