## Why

Four consecutive pre-release audit rounds found the same defect in the same component, each time in a
different disguise: `provision check`/`apply` decide whether `pg_hba.conf` grants a blanket `trust` by
matching the file's text, and the text has more shapes than the matcher knew.

- Round 4: a trust written `localhost` / `samehost` / `samenet` survived, and the check reported the host as
  narrowed.
- Round 5: indented lines, `hostnossl`, and the `address netmask` form survived.
- Round 6: `all`, `0.0.0.0/0` and `127.0.0.0/8` survived — addresses that contain loopback without naming it.
- Round 7: `hostssl` survived, which on the supported host (`ssl = on`, clients prefer TLS) is **the rule a
  loopback connection is matched against**. The closing connection check passed *because of* the rule that
  should have been removed, and `provision check` printed `trust for odoo only`.

Each fix was correct and each left the same hole open somewhere else, because a re-implementation of
PostgreSQL's parser is being asked to be exhaustive about a format it does not own. Records can also span
lines, pull in other files, and carry comma-separated or regex-valued fields — all of which the tool
currently refuses (round 7) rather than misreads, which is honest but is still a refusal.

PostgreSQL parses this file for a living and exposes the result: `pg_hba_file_rules` (PostgreSQL 10+, with
`file_name`/`rule_number` from 15) returns one row per effective rule, with `type`, `database`, `user_name`,
`address`, `netmask`, `auth_method` and `error`, resolving continuations and `include`/`include_dir` and
attributing each rule to its source file. The only supported host runs PostgreSQL 16.

## What Changes

- `provision check`'s loopback-auth probe reads `pg_hba_file_rules` instead of parsing `pg_hba.conf`, and can
  therefore answer for files it previously reported as unknown (continuations, `include*`), naming the file a
  rule came from.
- `provision apply` verifies its own rewrite against the same view after reloading: no rule trusting every
  role may remain, and the development role's rule must precede any rule that matches the same connection.
  The live connection check stays as the final word.
- The rewriter keeps writing text (there is no SQL interface that edits the file), including its refusal to
  touch a file whose rules it cannot read line by line.
- `tools/verify_pg_hba_trust.py` asserts against a throwaway PostgreSQL cluster it creates and destroys,
  instead of against a regex written alongside the code it checks.

## Impact

- Affected specs: `provision-check`, `provision-apply`.
- Affected code: `odoo_dwg/system.py` (the probe becomes a query), a new pure `odoo_dwg/pghba.py`
  (classification), `odoo_dwg/planners.py` (post-write verification), `tools/verify_pg_hba_trust.py`.
- No runtime dependency is added: the query goes through `psql`, which is already a host prerequisite.
- A host whose PostgreSQL is not running still reports the state as unknown, exactly as today.
