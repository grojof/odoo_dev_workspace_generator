# provision-apply Specification Delta

## ADDED Requirements

### Requirement: The narrowing is verified against the server

After reloading PostgreSQL, `provision apply` SHALL ask the server what rules it now has
(`pg_hba_file_rules`) and SHALL fail the step when either is true:

- a TCP rule trusting every role remains — naming the file and line it is on, which may be an included file
  the rewriter never saw;
- the first rule PostgreSQL matches for the development role is not the trust rule the step added — naming
  the rule that matches first.

This check is written against a different source of truth than the text the step wrote, because every defect
this feature has had took the form of a step reporting a success that had not happened. The live connection
check remains the last command.

#### Scenario: A trust the rewriter could not reach is caught

- **WHEN** a blanket trust lives in a file pulled in with `include_dir`, so the rewrite did not touch it
- **THEN** the step fails naming that file and line, rather than reporting the host as narrowed

#### Scenario: A rule that matches first is caught

- **WHEN** a rule for a group role the development role belongs to precedes the added trust rule
- **THEN** the step fails naming the rule PostgreSQL matches first

#### Scenario: A narrowed host passes

- **WHEN** the rewrite left exactly the development role's trust rule ahead of every rule for all roles
- **THEN** the verification passes and the connection check runs
