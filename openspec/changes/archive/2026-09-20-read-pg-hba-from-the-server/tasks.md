# Tasks

## 1. Read the rules from the server

- [x] 1.1 Add `odoo_dwg/pghba.py` (pure): a `Rule` record, a parser for the view's tab-separated output, and
      the classification — `blanket_trust(rules)` and `role_is_reached(rules, role)` — with the quoted-field
      guard applied by the caller that has the file's text.
- [x] 1.2 `system.pg_hba_rules(port)`: query `pg_hba_file_rules` through `sudo -n -u postgres psql -w`,
      returning parsed rules or None when the server is down, the view is unavailable, or a rule carries an
      `error`.
- [x] 1.3 Rewrite `system.pg_hba_loopback_state` on top of both, keeping its `(blanket, role_reached) | None`
      contract so `provisioning` and `workflows/provision` need no change.
- [x] 1.4 Unit tests for the pure parser and classifier, including a quoted `"all"` rule, a rule from an
      included file, and a rule carrying an `error`.

## 2. Verify the rewrite

- [x] 2.1 `planners.plan_pg_hba_trust` gains a verification command after the reload: the view must show no
      rule trusting every role, and the role's rule must precede any rule matching the same connection.
- [x] 2.2 The failure message names the file and line the offending rule came from.
- [x] 2.3 Keep the live connection check as the last command.

## 3. Verify against PostgreSQL, not against ourselves

- [x] 3.1 `tools/verify_pg_hba_trust.py`: create a throwaway cluster (`initdb`, spare port, socket in the
      temp directory), point it at each fixture, `pg_reload_conf()`, and assert with the view and with a
      real connection.
- [x] 3.2 Skip with a clear message when `initdb` is not on the host, keeping the text-only assertions.
- [x] 3.3 Keep the fixtures the writer still needs (no trailing newline, continuations, includes).

## 4. Documentation

- [x] 4.1 Update the `provision-check` and `provision-apply` delta specs.
- [x] 4.2 `docs/provisioning.md`: what the check reads, and what apply verifies.
- [x] 4.3 `CONTRIBUTING.md`: what the pg_hba verifier now needs and does.
- [x] 4.4 `CHANGELOG.md` under `[Unreleased]`.
