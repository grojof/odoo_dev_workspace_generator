# Proposal

## Why

The first client migration found its worst problems by hand, with ad-hoc queries run between steps. Those
problems were:
- journal codes the target's unique constraint refuses;
- bank statement lines imported twice;
- unreconciled lines whose payment was already posted on the bank account, which 14.0+ counts twice;
- statement lines OpenUpgrade 14.0 leaves stored as reconciled;
- required fields left empty, including an SII certificate without its file;
- a declared unique constraint that OpenUpgrade only logged as "unable to add".

Every one of them is generic: any migration can hit them, and none is visible from the step's success.
The tool already fixes several of them, but nothing lets an operator, or an assistant, ask one database
"which of these do you have?" and get the same answer every time.

## What Changes

- A new read-only command, `odoo-dwg migrate audit --database <db>` (with `--db-host`, `--db-port` and
  `--db-user`, as `mail check` has). It runs a fixed catalogue of coherence checks against one database.
  It writes nothing, prompts for nothing, and exits **0** when nothing was found, **1** when a check
  found something, and **2** when it could not tell.
- Each check first reads the catalogue and decides whether it applies, from the tables and columns the
  database has, not from a version the operator states. So the same command works on:
  - a source copy before the chain;
  - a checkpoint between steps;
  - the migrated database.

  The checks:
  - **journal codes**: journals of one company that share a code, which `unique(company_id, code)` refuses
    from 15.0. Codes that differ only by case or spaces are information;
  - **bank lines imported twice**, for a source up to 13.0 (the intake's proof);
  - **payments posted on the bank account**, for a source up to 13.0: unreconciled statement lines matching
    a posted payment line on their journal's bank account by amount. These are counted twice from 14.0.
    They are split between closed and open periods;
  - **closed-period unreconciled lines**, for a source up to 13.0. Information only: whether to carry them
    is the client's accountant's decision;
  - **declared constraints missing**: unique and check constraints of installed modules that
    `ir_model_constraint` records but PostgreSQL does not have, as a constraint or a unique index. Names
    are compared as PostgreSQL truncates them (63 bytes);
  - **required fields left empty**: stored required fields of non-transient models holding NULL (for a
    binary field, no attachment and no column value). They are split between active and archived records.
    Archived-only is information;
  - **statement lines stored as reconciled** while their entry still has a line on the journal's suspense
    account, from 14.0.
- For each finding, the output names the fix: the intake step, the decision, or the menu action. It
  applies none of them.
- A thin assistant skill, `.claude/skills/migration-coherence-check/`. It says when to run the command
  (before the chain, between steps on a checkpoint, after the chain) and how to read each check, and
  forbids re-deriving the checks by hand or copying client data anywhere in the repository.

Out of scope:
- fixing anything;
- foreign keys (`ir_model_constraint` keeps rows for tables long gone, so the check is noise);
- models whose table is not named after the model;
- checks that would need the target's sources.

## Capabilities

### New Capabilities

- `migration-audit`: the read-only coherence audit of one database, and its checks.

### Modified Capabilities

(none)

## Impact

- `odoo_dwg/audit.py` (new, pure): the catalogue query, each check's SQL, the parsers and the verdicts. It
  reuses the bank and journal queries of `odoo_dwg/intake.py`.
- `odoo_dwg/workflows/checks.py`, `odoo_dwg/cli.py`, `odoo_dwg/i18n.py`: the command.
- `.claude/skills/migration-coherence-check/SKILL.md`.
- Tests; a new verification against a throwaway PostgreSQL. A real 12 → 18 rehearsal is checked by hand:
  the unfixed run must show the journal constraint, the empty certificates and the payments without a
  journal, and the fixed run must not show the first two.
- `docs/migration.md`, `docs/commands.md`, `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `CHANGELOG.md`,
  `docs/roadmap.md`.
