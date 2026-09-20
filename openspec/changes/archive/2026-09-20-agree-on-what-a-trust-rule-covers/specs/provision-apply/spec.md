# provision-apply Specification Delta

## MODIFIED Requirements

### Requirement: Loopback trust for the development role only

`provision apply` SHALL give the development role a loopback (`127.0.0.1/32` and `::1/128`) `trust` line in
`pg_hba.conf`, so a workspace `odoo.conf` connects without a password, and SHALL put any blanket trust line
back to `scram-sha-256` — a blanket trust lets any local user connect as the `postgres` superuser.

This SHALL be planned whenever the rules are not already in that shape, **including on a host that already
has PostgreSQL and the role**, since those hosts are exactly the ones a previous version left with a blanket
trust. A blanket trust is what the `provision-check` capability defines, and SHALL be recognised here on the
same fields: any `host`, `hostssl`, `hostnossl`, `hostgssenc` or `hostnogssenc` rule whose **role field is
the keyword `all`** and whose method is `trust`, **on any database** and whatever address it names —
including addresses that contain loopback without naming it (`all`, `0.0.0.0/0`, `127.0.0.0/8`) and the
`address netmask` form, and however the line is indented. `hostssl` is not a corner case: the supported host
runs with `ssl = on` and libpq prefers TLS, so a `hostssl` record is the one a loopback connection is
matched against. A rule whose role field is quoted is a rule for a role *named* `all` and SHALL be left
alone; a quote on any other field SHALL NOT excuse the rule.

The role's own line SHALL be inserted *before* any rule that could match the same connection, since the
first matching rule wins, and the role SHALL be treated as trusted only when its line is **reached**, never
merely present.

When the file holds rules the *rewriter* cannot read one line at a time — a record continued with a trailing
backslash, or rules pulled in through `include`, `include_if_exists` or `include_dir` — the step SHALL
refuse to rewrite it, naming what it cannot see. Narrowing the rules it can read while leaving the rest
would report a success that did not happen. (The **check** reads such a file through the server and reports
it like any other; it is the text rewriting that has the blind spot.)

The role's line SHALL be appended on a line of its own: a file with no final newline would otherwise have
its last record fused with the first inserted rule.

The step SHALL fail rather than report success when it cannot place the line, whatever shape the file has.

After reloading PostgreSQL it SHALL ask the server what rules it now has (`pg_hba_file_rules`) and fail on
any of these, naming the file and line — which may be a file the rewriter never saw:

1. the server reports a rule it could not parse. It then refused to load the file and is still running the
   previous rules, while the file on disk reads as narrowed. `pg_ctl reload` returns success either way, so
   nothing else in the plan would notice;
2. a TCP rule still trusts every role — unless that rule's own line quotes its **role field**, since `"all"`
   is a role literally named `all` and not the keyword;
3. a TCP trust rule names its roles by pattern (`/…`) or group (`+…`), which this step cannot rule out;
4. the first rule PostgreSQL matches for the development role is not the plain `host` trust rule the step
   added.

That check is written against a different source of truth than the text the step wrote, because every defect
this feature has had took the form of a step reporting a success that had not happened.

It SHALL then end by connecting as the role over loopback — `pg_hba.conf` is first-match-wins, so a line that is
present but shadowed by an earlier rule is not a narrowing.

Every probe behind these decisions is a tri-state, and an answer that could not be obtained SHALL be treated
as "do the work", never as "already done": a stopped server hides both the role and the file. Every planned
step SHALL be idempotent, so acting on an unknown costs a no-op.

The rewriter, the check and the verification SHALL agree on what *reaches* the role, **field by field and
not by the shape of a line**: the rule a connection meets is the first TCP rule whose role field is the role
or the keyword `all`, and the role is trusted only when that rule is its own plain `host … trust` rule for
every database. A rewriter that read this differently would insert nothing and then fail a verification that
re-running cannot fix.

#### Scenario: An already-provisioned host is narrowed

- **WHEN** apply runs on a host that has PostgreSQL, the role, and a blanket loopback `trust`
- **THEN** the plan contains the `pg_hba` narrowing even though nothing needs installing

#### Scenario: Nothing to narrow

- **WHEN** the role already has its loopback trust line and no blanket trust exists
- **THEN** no `pg_hba` command is planned

#### Scenario: The line cannot be placed

- **WHEN** the file has no rule the insertion can anchor to and the line cannot be appended
- **THEN** the step exits non-zero naming the file, rather than leaving the role unable to connect

#### Scenario: A trust spelled another way is still blanket

- **WHEN** `pg_hba.conf` trusts every role on `localhost`, on `all`, or on `0.0.0.0/0` rather than
  `127.0.0.1/32`, or on one database rather than every database
- **THEN** each of those lines is narrowed too, and the check does not report the host as already narrow

#### Scenario: A TLS rule is still a trust

- **WHEN** `pg_hba.conf` holds `hostssl all all 127.0.0.1/32 trust`
- **THEN** it is narrowed like any other blanket trust — it is the rule a loopback connection actually
  matches on a host with `ssl = on`

#### Scenario: A shadowing rule the rewriter did not expect

- **WHEN** `pg_hba.conf` holds a rule matching the role's loopback connection above its trust line, and that
  rule is not `host all all`
- **THEN** the rewriter inserts the role's line above it, and the verification step passes — rather than
  reporting success and then failing on a file that re-running cannot change

#### Scenario: A trust rule for the role on another connection type

- **WHEN** the role already has a `hostssl` trust rule and no plain `host` one
- **THEN** the step inserts its own plain `host` rule, rather than treating the existing one as the role's
  line and leaving the verification to fail

#### Scenario: A file whose rules cannot all be read is refused

- **WHEN** `pg_hba.conf` continues a record onto the next line, or pulls in rules with `include_dir`
- **THEN** the step exits non-zero naming what it cannot see, and leaves the file untouched

#### Scenario: A trust the rewriter could not reach is caught after the reload

- **WHEN** a rule trusting every role remains anywhere the server can see, the rewrite having missed it
- **THEN** the verification step fails naming that file and line, rather than reporting the host as narrowed

#### Scenario: A rule that PostgreSQL matches first is caught

- **WHEN** a rule naming every role, or the development role itself, precedes the added trust rule
- **THEN** the verification step fails naming that rule

#### Scenario: A rule naming roles by group is refused, not matched

- **WHEN** a `trust` rule names its roles by group (`+…`) or pattern (`/…`)
- **THEN** the pattern check refuses it, because the server reports the field verbatim and cannot say
  whether the development role is in it — the "matches first" check cannot answer for such a rule

#### Scenario: A role line that is present but never reached

- **WHEN** the role's trust line sits below a rule for every role that matches the same connection
- **THEN** the check reports the role as not trusted, and apply inserts a line that is reached

#### Scenario: The role's line is shadowed by an earlier rule

- **WHEN** the role's trust line is added but an earlier rule matches the same loopback connection first
- **THEN** the closing connection check fails the step, instead of reporting a narrowing that does not work

#### Scenario: PostgreSQL installed but stopped

- **WHEN** apply runs on a host where PostgreSQL is installed, its service is down, and the role therefore
  cannot be probed
- **THEN** the plan starts the service and creates the role if missing, rather than reporting the host as
  already provisioned
