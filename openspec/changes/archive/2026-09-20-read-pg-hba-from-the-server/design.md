## Context

`pg_hba.conf` is PostgreSQL's format, not ours. Four audit rounds established, with worked examples, that
deciding "does this file grant a blanket trust" by matching its text is a losing position: the format has
five TCP connection types, two address forms plus five keyword addresses, optional per-rule options,
comma-separated and regex-valued database/user fields, `@file` list includes, line continuations, and
`include`/`include_if_exists`/`include_dir`. Each round's fix was right and each left another shape
unmatched — the last one, `hostssl`, being the shape the supported host actually uses.

## Goals / Non-Goals

- **Goal:** the answer to "is every role trusted over TCP, and is the development role's rule the one that
  wins" comes from PostgreSQL's own parser.
- **Goal:** `provision apply` proves its rewrite worked, rather than inferring it from the text it wrote.
- **Non-goal:** writing the file through SQL. There is no such interface; the rewriter stays `sed`/`awk`.
- **Non-goal:** interpreting whether an address covers loopback. Judging by *method* (round 6) made the
  address irrelevant to this question, and that stays true.

## Decisions

### Read the rules from `pg_hba_file_rules`, keep writing text

`SELECT type, database, user_name, auth_method, file_name, line_number, error FROM pg_hba_file_rules ORDER BY
rule_number` gives the effective rule set. Verified on PostgreSQL 16: it resolves line continuations into one
row, expands `include_dir` and attributes each rule to its source file, returns `database`/`user_name` as
arrays (so a comma-separated list arrives as elements), and re-reads the file at query time rather than
serving the loaded configuration — which makes it usable both before and after a reload.

**What this does not fix, and how we handle it:**

- *It cannot write.* The insertion and the downgrade stay text. Their own defects (append on a file with no
  trailing newline, insertion anchored too late) were fixed separately and are covered by fixtures.
- *Quoting is normalised away.* `host "all" "all" 127.0.0.1/32 trust` arrives as `database=all, user=all`,
  indistinguishable from the keyword — yet PostgreSQL does **not** treat it as every role (verified: such a
  rule above a `reject` does not let the role in). The view alone would call it a blanket trust and downgrade
  a rule for a database literally named `all`. We therefore keep one textual guard: a rule whose own line
  carries a quoted field is not classified as blanket. This is the one place text beats the view.
- *It does not report the rules in force.* There is no view for the loaded set, so the live connection check
  after the reload remains the final word and is not dropped.
- *It needs a running server and superuser access.* Both are already true of this probe: it goes through
  `sudo -n -u postgres psql`, and `gather_facts` only probes when PostgreSQL is running. A stopped server
  still yields the unknown state, which `provision apply` treats as "do the work".

### Verify the rewrite, do not infer it

After `systemctl reload postgresql`, apply queries the view again and fails the step when a rule trusting
every role remains, or when the development role's rule does not precede one that matches the same
connection. Every previous round's bug was "the step reported success"; this is the check that makes success
mean something, and it is written against a different source of truth than the writer.

### Make the verifier's oracle a real PostgreSQL

`tools/verify_pg_hba_trust.py` asserted with a regex copied from `system.py`, so every shape both missed
passed as correct — which is exactly how `hostssl` survived three rounds of a tool written to stop this bug
class. It now reads records by field (independent of the implementation) and, for the classification
questions, stands up a throwaway cluster (`initdb` in a temp directory, a spare port, a unix socket inside
that directory, destroyed afterwards) and asks PostgreSQL. No network, nothing outside the temp directory,
and the host's own cluster is never touched.

## Risks / Trade-offs

- **The verifier now needs PostgreSQL binaries on the host.** It already needs `bash` and `sed`; a developer
  running it has PostgreSQL because `provision apply` installs it. The tool skips with a clear message when
  `initdb` is absent, rather than failing.
- **One more moving part in a probe that must never prompt.** The query uses `sudo -n` and `-w` like the
  existing probes, and any failure returns the unknown state.
- **The text path does not disappear**, so the shapes it must still handle (writing) keep their fixtures.
