# Proposal

## Why

Up to 12.0 a localisation can model a reverse charge or an intra-community purchase as a group tax with two
children, and the accounts are the children's. OpenUpgrade 13.0 (`l10n_es` 13.0.4.0) turns each such group
into one tax, creates its repartition lines and takes their account from the group, which holds none. The
journal items that existed keep their accounts, but a bill posted after the migration puts both tax amounts
on the expense account of its line. It was reproduced on a clean 12.0 database with `l10n_es`, and proposed
upstream (OCA/OpenUpgrade#6047).

OCA's `account_chart_update` fills the template's accounts when run at 13.0. A chain that goes on without it
keeps the lines without account, and at 18.0 the wizard stops on a tax already used. Data checks do not see
it: only new documents are affected.

## What Changes

- **Right after the 13.0 step**, for a source up to 12.0, each tax repartition line of a former group tax
  that has no account takes the account of its child's repartition line, matched by document, repartition
  type and sign, as OpenUpgrade matches the journal items. An account the database already has stays, so
  with the upstream fix merged nothing is written.
- **Every line written is listed** in `logs/13.0-group-tax-accounts.tsv`.

## Capabilities

### Modified Capabilities

- `migration-run`: a repair after the 13.0 step.

## Impact

`odoo_dwg/grouptaxes.py` (new), `odoo_dwg/templates.py`; `tests/test_grouptaxes.py`;
`tools/verify_group_tax_accounts.py`; docs.
