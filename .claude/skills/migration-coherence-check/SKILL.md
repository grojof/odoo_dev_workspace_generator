---
name: migration-coherence-check
description: Check one Odoo database for the data problems that break or distort an OpenUpgrade migration - journal codes the target's unique constraint refuses, bank lines imported twice, payments the bank would count twice, declared constraints PostgreSQL does not have, required fields left empty, statement lines stored as reconciled. Use before the chain on a client copy, between steps on a checkpoint, after the chain on the migrated database, or when asked whether a migrated database is coherent.
license: AGPL-3.0-or-later
compatibility: Requires odoo-dwg on PATH (or `python -m odoo_dwg`) and a database the role can read.
metadata:
  author: odoo_dwg
  version: "1.0"
---

One command. It only reads: it writes no file and changes nothing in the database.

```bash
odoo-dwg migrate audit --database <db> --lang en
# a restored reference read by its reader role:
odoo-dwg migrate audit --database <db> --db-user <reader> --lang en
```

Exit **0** nothing found, **1** a check found something, **2** could not tell: a check was unreadable,
the database could not be read, or it is not an Odoo database.

**Do not write these queries yourself.** Each check is the same SQL the tool's intake steps and repairs
use, so the audit and the fix agree on what is affected. Hand-written variants have been wrong before: an
information_schema catalogue that hides unreadable tables, constraint names compared without PostgreSQL's
63-byte truncation, and foreign-key rows of tables long gone reported as missing.

## When to run it

- **Before the chain**, on the client's reference copy: journal codes, the three bank-line checks.
- **Between steps**, on a restored checkpoint (`checkpoints/<version>.dump`): shows at which step a
  constraint or a required field went wrong.
- **After the chain**, on the migrated database: constraints, required fields, the reconciled flag.

Checks apply by the shape of the database, not by a version you state. "Not applicable" means the check
does not concern this database. It is not a pass.

## Reading it

- **`found`** (WARN): lead with these. Each names its fix: an intake step, a data correction on the working
  copy, or the client's accountant's decision.
- **`info`**: worth saying, and it does not change the exit code:
  - codes differing only by case or spaces;
  - unreconciled lines of closed periods, which the client's accountant decides whether to carry;
  - required fields empty only on archived records.
- **`could not be read`** (ERROR): say which, and do not call the database clean.

Two findings need care in how you word them:

- **Payments posted on the bank account**: an equal amount is a candidate, not proof. The client's
  accountant reconciles them in the source before the final copy. The open-period count is the one that
  changes from day to day.
- **Declared constraints missing**: OpenUpgrade logs "unable to add constraint" and carries on. The fix is
  in the data before the step that adds the constraint, never in dropping the constraint.

## Rules

- **Change nothing, and run nothing that changes anything.** The fixes are menu actions, intake steps and
  the client's decisions. Name them.
- **Client data stays out of the repository.** The output carries a client's journal codes, ids and
  amounts. Quote it to the operator, and never put it in code, tests, specs, docs, commits or pull requests.
  Examples there use invented or Odoo demo data (`BANK1`, `CSH1`, "Acme Corporation", "My Company").
- Background: `docs/migration/checks-findings.md`.
