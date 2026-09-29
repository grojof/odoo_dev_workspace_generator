## MODIFIED Requirements

### Requirement: A dropped module can be retired before the chain, and named losses accepted

A `dropped` or `replaced` decision MAY carry `"when": "before-chain"`. Any other value of `when`, or `when` on
another kind of decision, SHALL be refused by name. `migrate decide MODULE --decision dropped --before-chain`
SHALL record it, and without `--write` only print the entry; so SHALL `--decision replaced --to …
--before-chain`.

A `replaced` decision retired before the chain MAY name the module itself in `to`: a module that has no code
at a step of the chain, but has at the target, leaves before the chain and is installed again at the target.
Naming itself in `to` SHALL be refused on any other decision.

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

#### Scenario: A module with a gap in the chain, installed again at the target

- **WHEN** the operator runs `migrate decide acme_check --decision replaced --to acme_check --before-chain
  --write`
- **THEN** the decisions file holds a `replaced` entry for it with `"to": ["acme_check"]` and
  `"when": "before-chain"`, and no problem is named

#### Scenario: A module carried to itself without leaving before the chain

- **WHEN** a `replaced` decision names the module itself in `to` and carries no `when`
- **THEN** the decision is refused as carried to itself
