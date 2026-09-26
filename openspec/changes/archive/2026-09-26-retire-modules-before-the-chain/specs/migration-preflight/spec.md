# Spec Delta

## ADDED Requirements

### Requirement: A dropped module can be retired before the chain, and named losses accepted

A `dropped` decision MAY carry `"when": "before-chain"`. Any other value of `when`, or `when` on another kind
of decision, SHALL be refused by name. `migrate decide MODULE --decision dropped --before-chain` SHALL record
it, and without `--write` only print the entry.

The decisions file MAY hold an `accepted_losses` list, beside its decisions. Each entry names a table, or a
`table.column`, of the source database, with the source and target versions and the reason. `migrate
accept-loss TABLE[.COLUMN] --reason …` SHALL record one, replacing the entry for the same name and pair, and
without `--write` only print it. A name that is not a table or `table.column` identifier SHALL be refused.

#### Scenario: Retiring a module before the chain

- **WHEN** the operator runs `migrate decide web_diagram --decision dropped --before-chain --write`
- **THEN** the decisions file holds a `dropped` entry for it with `"when": "before-chain"`, and every other
  entry is left as it was

#### Scenario: A loss accepted by name

- **WHEN** the operator runs `migrate accept-loss account_journal.group_method --reason "…" --write`
- **THEN** the decisions file's `accepted_losses` holds that column with its reason
