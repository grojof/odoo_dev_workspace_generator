# Design

## What the server actually does

Every decision below was settled by loading a fixture into a throwaway PostgreSQL 16 cluster and asking it
two things: what `pg_hba_file_rules` reports, and whether a TCP connection is accepted.

| `pg_hba.conf` rule | View reports | TCP connection as `postgres` |
|---|---|---|
| `host all all 127.0.0.1/32 trust` | `all` / `all` | accepted to any database |
| `host mydb all 127.0.0.1/32 trust` | `mydb` / `all` | refused to `postgres`, **accepted to `mydb`** |
| `host all all "127.0.0.1/32" trust` | `all` / `all` | **accepted** — a quoted address is still that address |
| `host "all" "all" 127.0.0.1/32 trust` | `all` / `all` | refused — quoted `all` is a name |
| `host all "all" 127.0.0.1/32 trust` | `all` / `all` | refused — the *role* field is what decides |

Two facts follow. The view cannot tell a keyword from a quoted name, so the line's own text stays the
tie-breaker — but only for the **role** field, because that is the only field whose quoting changed the
server's answer. And the database field never decides whether a rule is dangerous: connecting as `postgres`
to one database is enough to run `COPY … TO PROGRAM`.

## Why the role field, and not "every role" as a concept

A rule can reach every role without writing `all`: `/.*` matches by regex, `+group` by membership. Those are
already treated as *unknown* rather than as narrow, and that stays — this change is only about the keyword,
which is the one form that can be decided from the view plus one line of text.

## One definition, four implementations, and how they are kept in step

The question is asked in four places, for reasons that do not go away: the classifier is pure Python over
the view; the rewriter is `sed`/`awk` over the file, because it runs under `sudo` before anything is
loaded; the verification step is SQL, deliberately a different source of truth from the text the rewriter
wrote. Merging them is not possible. Making them agree *by field* is:

- **role field is the keyword `all`** → blanket trust. In Python, `"all" in rule.users` plus a line check;
  in the rewriter, a regex whose role field is a literal unquoted `all`; in SQL, `'all' = ANY(user_name)`
  plus the same line check.
- **the rule a connection meets** → the first TCP rule whose role field is the role or `all`. The rewriter's
  `awk` now splits fields and applies that, instead of matching the one line shape it knew.

`tools/verify_pg_hba_trust.py` is what holds them together: it runs the real rewriter script and the real
verification SQL over each fixture, against a server, and compares all three answers with an oracle that
reads the file's fields. A disagreement is a failing check, which is how disagreement 3 was found.

## The `awk` reach test

Field extraction has to mirror `pghba.Rule`: `type database user address [netmask] method`, where the
netmask is present only when the address carries no `/`. Written with `$1 … $NF` and no interval
expressions, so it behaves the same under `mawk` (Ubuntu's `awk`) and `gawk`.

It stops at the first rule matching the connection and answers there, rather than scanning on. That is what
`pg_hba` does, and it is why the previous version could report "reached" for a line PostgreSQL never gets
to.

## What is deliberately left alone

- **The address is still not interpreted.** `all`, `0.0.0.0/0` and `127.0.0.0/8` contain loopback without
  naming it; a rule trusting every role on any address is narrowed whatever it says.
- **A database named with a space** (`host "my db" all … trust`) is not matched by the rewriter's regex and
  is reported by the verification step as a rule it could not narrow, naming file and line. That is the
  existing posture for anything the text rewriting cannot see — a refusal that says so, rather than a
  silent pass.
