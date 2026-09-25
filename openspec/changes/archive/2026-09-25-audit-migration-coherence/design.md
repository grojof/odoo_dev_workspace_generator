# Design

## One command, any stage

The operator should not have to say what the database is. The command first reads one catalogue query:
the presence of the few tables and columns the checks depend on. Each check declares what it needs, and
applies only when the database has it:

| Check | Applies when | Why that marker |
|---|---|---|
| `journal-codes` | `account_journal` exists | 12.0 already names a constraint `account_journal_code_company_uniq`, but on `(code, name, company_id)`: the name cannot tell the versions apart, and the data check is cheap |
| `bank-duplicates`, `bank-payments`, `bank-closed-lines` | `account_bank_statement_line` has no `move_id` column | up to 13.0 an unreconciled line has no entry; the proof and the matching depend on it |
| `constraints-missing` | `ir_model_constraint` exists | any version |
| `required-empty` | `ir_model_fields` has `required` and `store` | any version |
| `statement-lines-reconciled` | `account_bank_statement_line.is_reconciled` and `account_journal.suspense_account_id` exist | 14.0 and later |

A check that does not apply is reported as "not applicable", never as passed.

Journals of one company **sharing** a code are a finding: from 15.0 `unique(company_id, code)` refuses
them, and OpenUpgrade only logs that it could not add the constraint. Codes that differ **only by case or
spaces** are information: accepted, but easy to confuse.

## Reuse, not restatement

The bank checks run the intake's own `BANK_DUPLICATES_SQL` and `BANK_LOCKED_SQL`. The journal check runs
`JOURNAL_CODES_SQL` and `journal_code_plan`. The reconciled-flag check selects the same lines as the 14.0
repair (`templates._STATEMENT_LINES_REPAIR`), with its SQL taken out as a shared constant. So the audit
and the fix always agree on what "affected" means.

## Constraints: why unique and check only

`ir_model_constraint` keeps foreign-key rows for many-to-many tables and models long removed. On a real
migrated database there were hundreds of "missing" foreign keys, none of them real. Unique and check
constraints (`type = 'u'`) are the ones whose absence means data the model forbids. On the same database,
the run without the journal-code rename showed exactly one: `account_journal_code_company_uniq`.

A constraint counts as present when `pg_constraint` or a unique index has its name truncated to 63 bytes,
as PostgreSQL stores it. Only rows of installed modules whose table exists are read. The table is taken as
the model name with dots replaced by underscores, so a model with its own `_table` is skipped, not
reported.

## Required fields: two passes

A required field whose column is `NOT NULL` cannot hold NULL, so only the others need counting.

- **First pass:** the candidates. These are the stored, required, non-x2many fields of non-transient
  models, whose column exists and is nullable. Required binary fields are candidates too, because
  attachment-stored binaries have no column.
- **Second pass:** one `UNION ALL` of counts, built from the candidates. Each branch gives total and
  active rows, the latter only when the table has an `active` column. For a binary field, a record
  counts as empty when there is no `ir_attachment` for it (`res_model`, `res_field`, `res_id`) and, if the
  column exists, the column is NULL.

Every identifier in the second query comes from the catalogue. It is still checked against
`^[a-z_][a-z0-9_]*$` and double-quoted, so a strange name cannot reach the SQL.

A field empty only on archived records is information, not a finding: an archived operation type without a
default location changes nothing. This covers the SII certificate without its file on its own, so the audit
has no SII-specific check.

## The payment check

These are unreconciled lines (no journal item points at them) for which a posted payment line exists:
- on the same journal;
- on the journal's default debit or credit account (the bank account in 12.0/13.0);
- linked to no statement line;
- for the same amount.

An amount match is not proof, and the output says so. The list per line is for the client's accountant,
and the operator produces it. The counts are split by the company's lock date, because a closed period is
the accountant's decision. On a real copy it reported the same lines as the analysis done by hand.

## Output and exit code

One block per check. Each gives the verdict (`found`, `clean`, `info`, `not applicable`, `unreadable`),
the count, up to ten examples (ids, codes, models), and for a finding, what to do (the intake step, a
decision, or a menu action). Examples carry ids and codes, never partner names or labels, so the output can
be pasted into an issue.

Exit 1 if any check found something. Otherwise exit 2 if any check was unreadable. Otherwise exit 0.
Information does not change the exit code.

## Each check its own query

A failing query (a reader role without access to one table, a version shaped unexpectedly) makes that check
`unreadable` and leaves the others standing.
