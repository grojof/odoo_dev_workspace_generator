# Tasks

## 1. The ledger (pure)

- [x] 1.1 `odoo_dwg/findings.py`: dataclasses, `parse_ledger` collecting every problem into `LedgerError`,
      `dump_ledger` with a fixed key order; verify a round-trip test (`dump(parse(x)) == x`) and one test per
      refusal (unknown schema, bad id, unknown severity/audience/decision/phase state, missing evidence,
      missing query, duplicate or withdrawn id)
- [x] 1.2 Operations `add_findings`, `decide` (history kept), `withdraw` (to corrections, id reserved),
      `set_phase`, each returning a new ledger; verify with tests for the "client changes their mind",
      "finding proves false" and "duplicate id" scenarios
- [x] 1.3 `MigrationEnv.findings_dir`, `findings_ledger`, `findings_data_dir`; verify with a path test

## 2. Rendering (pure)

- [x] 2.1 `i18n.translate(text, lang)` and the report labels in `_ES`; verify that `t()` still behaves as
      before and that `translate` ignores the session language
- [x] 2.2 TSV parsing of attached tables (header row required) and Markdown table rendering with per-language
      column labels; verify missing file / missing header are named
- [x] 2.3 `render_client_report`: phases, received, versions, pending questions, client findings by level
      with client tables, data handling, references; no internal or withdrawn content; refuses on missing
      client text in the report language; verify with the scenario tests
- [x] 2.4 `render_extended_report`: every finding in full with decision history, tables, evidence, query,
      corrections; verify with the scenario tests
- [x] 2.5 Determinism: verify the same inputs give identical bytes, and that a Spanish report is identical
      from an English and a Spanish session

## 3. Surface

- [x] 3.1 `system.url_status` (stdlib `urllib`, HEAD then GET on 405) and the ledger URL walk; verify the walk
      against a stubbed status function (private sources skipped), never the network
- [x] 3.2 Non-interactive `migrate findings list|show|validate|report|links` in `checks.py` + `cli.py`
      (`--report-lang`, exit 0/1/2, writes nothing); verify with CLI tests over a `tmp_path` ledger
- [x] 3.3 Menu Migration → Findings: start ledger, add from JSON, decide, set phase, withdraw, write
      reports — each through a previewed plan with confirmation; verify the plans are built as expected
- [x] 3.4 Operator strings through `t`/`tf` with Spanish entries; verify the catalog test passes

## 4. Docs and gates

- [x] 4.1 `docs/migration.md` (the ledger, its schema, the two reports), `docs/commands.md`, `README.md`,
      `CHANGELOG.md` `[Unreleased]`, `docs/roadmap.md`; verify every command shown runs as documented
- [x] 4.2 Gates: `pytest`, `ruff`, `openspec validate --specs`, `python -m odoo_dwg --help`, and the
      generated-shell verifier

## 5. The prototype ledger (on the host, outside the repository)

- [x] 5.1 Convert `~/odoo-migrations/12-to-18/findings/findings.json` to schema 1 (client text tagged `es`,
      decisions wrapped, bespoke tables turned into `tables` entries over client-ready TSVs); verify
      `migrate findings validate` exits 0
- [x] 5.2 Render both reports in Spanish and compare them with the prototype's; verify every difference is
      explained, then retire `generar_informes.py` and update the environment's `LEEME.md`
