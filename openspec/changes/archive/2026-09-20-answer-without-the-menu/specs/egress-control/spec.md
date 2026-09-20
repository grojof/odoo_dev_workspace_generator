# egress-control Specification Delta

## ADDED Requirements

### Requirement: The rules on the host can be checked against the rules the tool wrote

OpenSnitch evaluates rules in file-name order and the first match decides, which is why the tool's own
rules are named to sort first. Nothing checks that they still do. The system SHALL offer a read-only check
of the rules directory that reports:

- a rule the tool owns that is **absent** from the host;
- a rule the tool owns whose content **differs** from what the tool would write;
- a rule the tool owns that is **disabled**;
- a file in the rules directory that is **not readable as JSON**, since OpenSnitch's reading of it cannot
  then be predicted;
- a rule the tool does not own that **sorts before** the tool's own rules, because that is the only way a
  rule can be evaluated ahead of the one confining Odoo.

The check SHALL NOT modify or remove any rule, including one it reports, because a rule the operator wrote
deliberately to sort first is a legitimate thing to have and only the operator knows which it is.

#### Scenario: A rule that pre-empts the Odoo rule

- **WHEN** a rule file named `00-aaa-allow.json` exists beside the tool's `00-odwg-*` rules
- **THEN** the check reports it as sorting ahead of them, and changes nothing

#### Scenario: A rule that looks like it pre-empts and does not

- **WHEN** a rule file named `000-allow-everything.json` exists beside them
- **THEN** it is not reported, because `-` sorts before a digit and the tool's rules are still first — which
  is the whole reason the prefix is `00-odwg-`

#### Scenario: A hand-edited rule

- **WHEN** one of the tool's own rules no longer matches what the tool would write
- **THEN** the check reports that rule as changed

#### Scenario: Rules as the tool left them

- **WHEN** every owned rule is present, enabled and unchanged and nothing sorts before them
- **THEN** the check reports nothing
