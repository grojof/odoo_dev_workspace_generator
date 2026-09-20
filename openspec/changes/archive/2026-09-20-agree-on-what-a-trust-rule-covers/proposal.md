# Change: Agree on what a trust rule covers

## Why

Reading the rules from the server fixed *where* rules are found. It left three disagreements about *what a
rule means*, each confirmed against a throwaway PostgreSQL 16 cluster rather than by reading the code:

1. **A trust for one database is invisible.** The classification requires the rule's database field to be
   `all` as well as its role field. `host mydb all 127.0.0.1/32 trust` therefore passes the check, survives
   apply and is accepted by the verification step. Against a real server, that rule lets any local user
   connect to `mydb` as `postgres` — superuser, `pg_execute_server_program` included, which is command
   execution as the `postgres` account. The database field bounds *which database* is exposed, never
   *whether* it is.

2. **The quoted-field exception is wider than the fact it exists for.** `"all"` is a name, not the keyword —
   the server refuses a TCP connection matched only by `host "all" "all" 127.0.0.1/32 trust`, so a rule
   whose role field is quoted is correctly not a blanket trust. But the exception is implemented as *any
   double quote anywhere on the rule's line*, and PostgreSQL accepts a quoted address: `host all all
   "127.0.0.1/32" trust` is a live blanket trust — the same cluster accepts the connection — that the check
   reports as narrow and the verification step passes over.

3. **The rewriter and its own verification disagree about what *reaches* the role.** The rewriter decides
   whether to insert the role's line with an `awk` that stops at one shape, `host<type> all all`; the check
   and the verification step stop at the first rule matching the same connection, whatever its shape. On a
   file holding `host mydb all 127.0.0.1/32 md5` above the role's trust line — or the role's own
   `scram-sha-256` rule above its trust line — the rewriter reports success having inserted nothing, and the
   verification step then fails: *the first rule PostgreSQL matches for odoo is shadowed by …*. Re-running
   produces the same two answers, so `provision apply` cannot complete on that host at all. Both cases were
   reproduced end to end.

The three share one cause: the same question — *does this rule trust every role, and is it the rule the
connection meets?* — is answered in four places (the pure classifier, the rewriter's regexes, the rewriter's
`awk`, the verification SQL) and the answers were never made to agree field by field.

## What Changes

- A blanket trust is **any TCP rule whose role field is the keyword `all` and whose method is `trust`**, on
  any database and any address. The classifier, the rewriter's regex and the verification SQL all widen.
- The quoted-field exception narrows to the field it is about: a rule is not a blanket trust when **its
  role field is quoted**, decided from the line's own text with a quote-aware match. A quote anywhere else
  on the line no longer excuses it.
- The rewriter decides *reached* by fields, exactly as the classifier and the verification step do: the
  first TCP rule whose role field is the role or `all` is the rule the connection meets, and the role is
  trusted only when that rule is its own plain `host … trust` rule for every database.
- `tools/verify_pg_hba_trust.py` gains the three fixtures above, and its oracle widens with the definition.

## Impact

- Affected specs: `provision-check` (loopback authentication reporting), `provision-apply` (loopback trust
  for the development role only).
- Affected code: `odoo_dwg/pghba.py`, `odoo_dwg/planners.py`, `odoo_dwg/system.py`,
  `tools/verify_pg_hba_trust.py`, `tests/test_pghba.py`.
- Operator-visible: a host with a per-database trust for every role now reports WARN and is narrowed by
  apply; a host whose `pg_hba.conf` shadows the role's line with something other than `host all all` can be
  provisioned at all, which it could not before.
