# Tasks

## 1. The repair

- [x] 1.1 `ungroup.py`: reused source items (matched invoice line) kept out of the zero-amount lines; the
      references found before the groups; OCA's stored analytic accounts among the line's own tables; the
      detail check. Verified by `tests/test_ungroup.py`.
- [x] 1.2 `tools/verify_grouped_invoice_lines.py`: a reused source item at zero keeps its zero, taxes and
      box; without the flag, a repair that would change a box's detail keeps nothing. Verified by the tool
      passing.

## 2. Validation and docs

- [x] 2.1 On the first client's parity copy, rolled back: the repair commits its checks with reused items
      kept out.
- [x] 2.2 Docs: `docs/migration/running.md`, `CHANGELOG.md`; verified by `openspec validate`.
