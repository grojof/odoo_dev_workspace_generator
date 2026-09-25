# Tasks

- [x] 1.1 `odoo_dwg/audit.py` (pure): the catalogue query and applicability, each check's SQL (reusing the
      intake's bank and journal queries, and the repair's statement-line selection moved to a shared
      constant), the required-fields second pass with validated identifiers, parsers and verdicts; tests
- [x] 1.2 `migrate audit` in `workflows/checks.py` and `cli.py`: each check its own query, output blocks,
      exit code; Spanish strings; tests with a stubbed `psql_rows`
- [x] 1.3 `tools/verify_migration_audit.py` against a throwaway PostgreSQL: a 12-shaped database (shared
      codes, a day imported twice, a payment on the bank, a closed-period line) and an 18-shaped one (a
      missing and a truncated constraint, a required binary without attachment, an archived-only NULL, a
      stale reconciled line), run through the real command; plus a failing check reported unreadable
- [x] 1.4 The skill `.claude/skills/migration-coherence-check/SKILL.md`
- [x] 2.1 Run it on the first client's source copy and both rehearsals, by hand; compare with the manual
      findings. Nothing from them enters the repository
- [x] 2.2 Docs: `docs/migration.md`, `docs/commands.md`, `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`,
      `CHANGELOG.md`, `docs/roadmap.md`
