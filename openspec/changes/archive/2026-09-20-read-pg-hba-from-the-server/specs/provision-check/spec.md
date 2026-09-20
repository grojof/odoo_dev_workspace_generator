# provision-check Specification Delta

## MODIFIED Requirements

### Requirement: Loopback authentication reporting

The check SHALL report how loopback authentication is configured for the development role, reading the rules
**from the server** (`pg_hba_file_rules`) rather than parsing `pg_hba.conf`. PostgreSQL's own parse folds
continued records, expands `include`, `include_if_exists` and `include_dir`, splits list-valued fields, and
names the file each rule came from — so a rule this tool could not previously see is reported like any
other.

A blanket trust — any TCP rule (`host`, `hostssl`, `hostnossl`, `hostgssenc`, `hostnogssenc`) for every role
whose method is `trust`, whatever address it names — SHALL be reported as a WARN naming what apply would do;
a role whose trust rule is not the one a connection **reaches** as INFO; and the narrowed state as OK.

A rule whose own line quotes its database or role field SHALL NOT be treated as a blanket trust: `"all"` is
a database or role literally named `all`, which the view reports exactly like the keyword.

When the state cannot be had — PostgreSQL is not running, the view cannot be read without a password, or the
server reports a rule it could not parse — the row SHALL say so rather than claim either state.

#### Scenario: Blanket trust is called out

- **WHEN** `pg_hba.conf` trusts every role over TCP
- **THEN** the row is WARN and says apply narrows it to the development role

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

- **WHEN** a rule reads `host "all" "all" 127.0.0.1/32 trust`
- **THEN** it is not reported as a blanket trust, because PostgreSQL does not treat a quoted field as the
  keyword
