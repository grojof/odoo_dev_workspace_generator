# Proposal

## Why

The first real client intake (Odoo 12 → 18) produced many findings before any step ran: a tax-reporting
module in production mode with invoices pending, overdue crons, mail that had not left for years, a core
that was OCB rather than official Odoo, OCA modules missing at intermediate steps. They lived in chat and in
a hand-written JSON file and report script outside the repository, and two of them had to be corrected:
one withdrawn (a module "without code" that used a legacy manifest name) and one count quoted from
memory instead of re-derived. A migration needs one place where every finding is recorded, together with
the evidence behind it, the query that re-derives it, and the client's decision on it. That place must
produce the reports shown to the client before, during and after the migration, and those reports must
never be edited by hand. The next two changes, neutralising a production copy and taking in a client
copy, need that place to write to. Building it first means they write straight into it.

## What Changes

- A **findings ledger** per migration environment, `<env root>/findings/findings.json`, with a versioned
  schema:
  - **one entry per finding:** id, date found, phase, severity, category, audience (client or internal),
    subject, technical summary, structured evidence, the query or command that re-derives it, the
    proposed action, the decision, optional client-facing text per language, and optional tables
    attached from `findings/data/*.tsv`;
  - **a context block:** what was received, the versions involved with reference links, and where the
    code comes from;
  - **the phases of the migration**, each with its state;
  - **a corrections log:** a withdrawn finding moves there with its reason, instead of disappearing.
- **Operator actions on the ledger:** list, show, add (from a JSON file), decide, set a phase's state, and
  withdraw. Every one of them is available from the menu and as a non-interactive command
  (`odoo-dwg migrate findings …`).
- **Two reports rendered from the ledger, never edited by hand:**
  - a **client report:** plain, semi-technical, with tables, links and the questions the client has to
    answer;
  - an **extended report:** every finding with its evidence, re-deriving query, action, decision and
    attached tables, plus the corrections log.

  Both are written to `<env root>/reports/`, in a language chosen for the report.
- A **link check** reads every URL in the ledger and reports those that do not resolve. It runs on the
  host, never in the test suite.
- **The prototype is imported.** The client's `findings.json` becomes the first ledger in the new
  schema, and the prototype `generar_informes.py` is retired.

Out of scope, and each belongs to its own later change:
- producing findings automatically (restore, outbound inventory, core identification, module
  availability; spec 3, the client intake);
- neutralising a copy (spec 2);
- exporting the reports to HTML or PDF.

Everything in this change is pure logic plus file writes in the environment, so it is fully testable
off-host. Only the link check needs the network.

## Capabilities

### New Capabilities
- `migration-findings`: the findings ledger of a migration environment — its schema and validation, the
  operator actions on it, the corrections log, and the client and extended reports rendered from it.

### Modified Capabilities
- `operator-interface`: "generated artifacts SHALL NOT be translated" gains one exception. A report
  written **for a client** is rendered in a language chosen for that report, independently of the UI
  language, with English as the default. Every other generated file stays English.

## Impact

- **New code:**
  - `odoo_dwg/findings.py`: pure schema, validation, ledger operations and report rendering;
  - `odoo_dwg/workflows/findings.py`: the actions;
  - CLI subcommands under `migrate findings`;
  - report labels in `odoo_dwg/i18n.py`;
  - `MigrationEnv.findings_dir`.
- **Tests:** schema round-trip and validation, each operation, both reports (including a report
  rendered in Spanish from an English session), and corrections.
- **Docs:** `docs/migration.md` (the ledger and reports), `docs/commands.md`, `README.md`,
  `CHANGELOG.md`, `docs/roadmap.md`.
- **No runtime dependency.** The link check uses `urllib` from the standard library.
- **Nothing AI-related is emitted.** The ledger is plain JSON that any tool can read.
