# provision-check Specification Delta

## MODIFIED Requirements

### Requirement: Loopback authentication reporting

The check SHALL report how loopback authentication is configured for the development role, reading the rules
**from the server** (`pg_hba_file_rules`) rather than parsing `pg_hba.conf`. PostgreSQL's own parse folds
continued records, expands `include`, `include_if_exists` and `include_dir`, splits list-valued fields, and
names the file each rule came from — so a rule this tool could not previously see is reported like any
other.

A blanket trust — any TCP rule (`host`, `hostssl`, `hostnossl`, `hostgssenc`, `hostnogssenc`) whose **role
field is the keyword `all`** and whose method is `trust`, **on any database** and whatever address it names
— SHALL be reported as a WARN naming what apply would do; a role whose trust rule is not the one a
connection **reaches** as INFO; and the narrowed state as OK. The database field bounds which database is
exposed, never whether it is: a rule trusting every role on one database lets any local user connect to it
as `postgres`, and a superuser in one database is a superuser on the host.

A rule whose own line quotes **its role field** SHALL NOT be treated as a blanket trust: `"all"` is a role
literally named `all`, which the view reports exactly like the keyword and which PostgreSQL does not match
a connection against. The exception SHALL be that field only — a quote elsewhere on the line, an address
written `"127.0.0.1/32"` included, leaves the rule a blanket trust, because the server reads it as one.

When the state cannot be had — PostgreSQL is not running, the view cannot be read without a password, the
server reports a rule it could not parse, or a TCP trust rule names its roles by pattern (`/…`) or group
(`+…`), which cannot be told to cover every role — the row SHALL say so rather than claim either state.

A role SHALL be treated as reached only through a plain `host` rule: the supported host runs with `ssl = on`
and clients prefer TLS, so a `hostnossl` rule is never consulted, and calling one "reached" would report a
host as narrowed where the role cannot connect at all.

#### Scenario: Blanket trust is called out

- **WHEN** `pg_hba.conf` trusts every role over loopback
- **THEN** the row is WARN and says apply narrows it to the development role

#### Scenario: A trust for one database is still a trust

- **WHEN** `pg_hba.conf` holds `host mydb all 127.0.0.1/32 trust`
- **THEN** the row is WARN, because any local user may then connect to `mydb` as `postgres`

#### Scenario: A trust in an included file is seen

- **WHEN** the blanket trust lives in a file pulled in with `include_dir`
- **THEN** the row reports it, because the server resolves the include

#### Scenario: A role line that is never reached is not narrow either

- **WHEN** the role's trust rule sits below a rule that matches the same connection
- **THEN** the row does not report the host as narrowed

#### Scenario: The state cannot be had

- **WHEN** PostgreSQL is not running, or the view cannot be read without a password
- **THEN** the row says so, never OK

#### Scenario: A role literally named all is not the keyword

- **WHEN** a rule reads `host all "all" 127.0.0.1/32 trust`
- **THEN** it is not reported as a blanket trust, because PostgreSQL does not match a connection against a
  quoted role field

#### Scenario: A quote somewhere else does not excuse the rule

- **WHEN** a rule reads `host all all "127.0.0.1/32" trust`
- **THEN** it is reported as a blanket trust, because the server accepts that connection like any other
