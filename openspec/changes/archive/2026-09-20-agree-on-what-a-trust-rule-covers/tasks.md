# Tasks

## 1. Widen the definition

- [x] 1.1 `pghba.blanket_trust`: a TCP `trust` rule whose role field is `all`, on any database.
- [x] 1.2 Replace `pghba.quotes_a_field` with a role-field test over the line's own text
      (`role_field_is_quoted`), quote-aware and applied to that field only.
- [x] 1.3 `system.pg_hba_loopback_state`: confirm each candidate through the new test; a line that cannot be
      read stays a blanket trust, so unknown is never read as narrow.

## 2. Make the rewriter agree

- [x] 2.1 `planners.BLANKET_TRUST_RULE`: any database, role field a literal unquoted `all`; keep the `sed`
      back-references in step with the new groups.
- [x] 2.2 Rewrite the `awk` reach test to split fields and answer at the first rule matching the connection,
      mirroring `pghba.role_is_reached` (mawk-safe: no interval expressions).
- [x] 2.3 `_pg_hba_audit`: drop the database condition, and replace the "any quote on the line" skip with a
      test that the role field is an unquoted `all`.

## 3. Prove it against a server

- [x] 3.1 `tools/verify_pg_hba_trust.py`: widen the field oracle with the definition.
- [x] 3.2 Fixtures: a per-database trust for every role; a blanket trust with a quoted address; a quoted
      role field; a shadowing rule that is not `host all all`; the role's own `scram` rule above its trust
      line.
- [x] 3.3 Audit cases for the quoted address (refused) and the quoted role field (accepted).
- [x] 3.4 Unit tests in `tests/test_pghba.py` for each new classification.

## 4. Document

- [x] 4.1 `CHANGELOG.md` under `[Unreleased]`.
- [x] 4.2 `docs/provisioning.md`: say what a blanket trust is, in the definition's new terms.
- [x] 4.3 `openspec validate --specs`, the full gate set, and `tools/verify_pg_hba_trust.py`.
