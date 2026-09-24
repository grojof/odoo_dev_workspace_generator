# Proposal

## Why

Taking in a client copy (the previous change) establishes what the client runs. It does not yet say three
things the first real intake had to answer by hand before any decision about the migration:

1. **What in the copy can act on the outside.** Crons, queued jobs, tax and EDI integrations, payment
   providers, IAP, mail. The neutralisation check already knows how to find each of these. Its answers are
   not yet findings the client report can show.
2. **Whether every installed OCA module exists at every step of the chain.** The first intake checked only
   the OCA repositories the client already used, and left its gaps provisional. A module can move to
   another repository between versions.
3. **Whether the client's own code talks to the network.** The database shows what is configured, but
   only the code shows what it does. The first intake's scan came back empty, and an empty scan is only
   believable if the scanner is shown to match what it looks for.

These three answers feed the client report and the migration's decisions: which modules to replace, drop
or port, and what to neutralise beyond the catalogue. The first intake did them with one-off scripts.

## What Changes

Three steps are added to **Migration → Take in a client copy**. Each one records findings and data
tables in the ledger, like the existing steps.

- **Survey what can act on the outside.** It runs the neutralisation check against the reference database
  as its owner (read-only) and turns each armed rule into a finding. The severity is declared per rule in
  the catalogue. The step also records:
  - the crons that are active and overdue, which all fire at the first start;
  - queued jobs by channel and state;
  - the outgoing mail queue by state, including mail that failed and would be retried if someone asked.
- **Check each installed module along the chain.** For every installed module of Odoo or of OCA, it
  follows the module through each step of OpenUpgrade: carried on, renamed or merged, using the existing
  fate reading. It then looks for the module's code at every step, first in the OCA repositories the
  client uses. For the steps where gaps remain, it looks in **every** OCA repository. The list of
  repositories comes from GitHub's organisation API. Each repository and version is cloned as a blobless
  tree (no file contents), cached per host, and a branch that does not exist is recorded as absent rather
  than retried. Any gap found in no OCA repository becomes a finding, and so does any module found in a
  different repository than at the source version.
- **Scan the client's own code for network calls.** It covers every installed module that is neither Odoo
  nor OCA, for imports and calls that reach the network or run processes (`requests`, `urllib`, `smtplib`,
  `ftplib`, `paramiko`, `zeep`, `socket`, `subprocess`, `xmlrpc`, job queue delays, …). **Before
  scanning, the scanner runs against a declared positive control.** If any pattern fails to match its
  control line, the step refuses to report "nothing found".

Out of scope: acting on what is found (neutralising is its own action), and porting code.

Verifiable off-host:
- rule severities, the survey's reading of rows, the availability walk and the scanner, by unit tests on
  invented fixtures;
- the availability walk against real git trees, by `tools/verify_intake.py` (extended).

On the host: the first client's copy, and the network, for the OCA repository list.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `client-intake`: three requirements are added:
  - the outbound survey as findings;
  - availability of every installed module at every step, across all OCA repositories;
  - the custom-code network scan, with its positive control.
- `copy-neutralisation`: each catalogue rule declares the severity of what it guards, so a survey can
  rank its findings.

## Impact

- **Code:**
  - `odoo_dwg/neutralise.py` (a severity per rule);
  - `odoo_dwg/intake.py` (the survey reading, the availability walk and the scanner, all pure);
  - `system.py` (the OCA organisation listing over `urllib`, and tree clones);
  - planners for the OCA tree clones;
  - `workflows/intake.py` (the three steps) and `i18n`.
- **Tests:** unit tests for each part. `tools/verify_intake.py` also checks availability against throwaway
  git repositories with a module that moves between repositories.
- **Docs:** `docs/migration.md`, `docs/commands.md`, `CHANGELOG.md`, `docs/roadmap.md`.
- **Network:** listing OCA's repositories (`api.github.com`) and cloning trees (`github.com`). Both are
  already allowed by the outbound firewall's development-infrastructure rule. No client system is ever
  contacted.
- **No runtime dependency. No client data in the repository.**
