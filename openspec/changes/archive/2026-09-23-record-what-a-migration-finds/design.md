# Design

## Context

The ESR intake built a working prototype outside the repository, in `~/odoo-migrations/12-to-18/`:
- `findings/findings.json` holds fourteen findings, a context block, phases and one correction;
- `findings/data/*.tsv` holds the tables those findings cite;
- `reports/generar_informes.py` renders both reports.

The prototype proved the shape of the ledger, but it is not the tool:
- it hard-codes ESR tables (SII states, crons, module fates) as bespoke render functions;
- it writes Spanish only;
- nothing validates the ledger it reads.

The codebase already has what this change needs:
- `write_text_file_command` for writing a file through a previewed plan;
- `MigrationEnv.reports_dir`;
- the non-interactive check commands in `workflows/checks.py`, which print and return 0/1/2;
- the i18n catalog, English → Spanish.

## Goals / Non-Goals

**Goals:**
- Turn the prototype into pure, tested code with no knowledge of any one client: every table comes from
  `findings/data/`, and no render function knows what an SII state is.
- Import the ESR ledger losslessly, so the first client's reports are the new renderer's first output.

**Non-Goals:**
- Producing findings. The intake change writes them through the same ledger operations.
- HTML or PDF. Markdown is readable as is, and converts with any tool the operator already has.

## Decisions

### 1. A pure `odoo_dwg/findings.py`, and I/O stays at the edge

`findings.py` holds:
- the dataclasses (`Ledger`, `Finding`, `Decision`, `Correction`, `Phase`, `TableRef`);
- `parse_ledger(text) -> Ledger`, which raises `LedgerError` listing every problem found, not only the
  first;
- `dump_ledger(ledger) -> str`;
- the operations (`add_findings`, `decide`, `withdraw`, `set_phase`), each returning a new `Ledger`;
- `render_client_report(ledger, tables, lang, today)` and `render_extended_report(...)`.

Tables arrive as parsed rows, so the renderers never open a file. `system.py` reads files and fetches
URLs. `workflows/findings.py` wires the two together.

**Alternative:** a class with methods that read and write files. It was rejected because every other
module here is pure plus a thin workflow, and a pure renderer is what makes the "same input, same bytes"
requirement testable.

### 2. Client text is keyed by language, and nothing falls back silently

The finding's `client` field is `{lang: {title, text, question, level?}}`. The prototype stored one
untagged Spanish block. The import tags it `es`.

A report in a language with no client text for a client finding refuses, naming the finding. Falling back
to the English technical summary would put text written for the operator in front of the client. The
operator adds the missing language instead; adding it is an edit to the ledger.

### 3. Tables are data, relabelled per language, never interpreted

A finding's `tables` entry is `{file, audience, title: {lang: …}, columns: {lang: [...]}?}`:
- `columns` relabels the header row for a language;
- values are printed verbatim.

The prototype translated values: `not_sent` became "No enviada", and "5 minutes" became "5 minutos". Under
this design, whoever produces a table meant for a client writes the client-ready values into it, one file
per language if needed. That keeps the renderer free of any one module's vocabulary.

**Alternative:** a value map in the ledger. It was rejected because a value map is a second translation
catalog living in data.

### 4. The report language is a parameter, not the session's

`i18n` gains `translate(text, lang)`, which is what `t()` already does with `_LANG` fixed. The renderers
call `translate(..., lang)` and never `t()`. A test renders a Spanish report from an English session and
from a Spanish session and compares the bytes: that is the operator-interface scenario.

The report labels ("Important", "What we need you to confirm", "Evidence", …) are English literals with
Spanish entries in `_ES`, authored in the same direction as the rest of the catalog.

### 5. Determinism: the date is an input

Both renderers take `today` from their caller. They never read the clock and never iterate an unordered
container:
- findings keep ledger order;
- groups follow a fixed level order;
- tables keep their row order.

The workflow passes `date.today()`.

### 6. Decisions keep their history in the finding

A finding's `decision` is a `Decision(state, date, note)`, and `history` lists the earlier ones. The
prototype's bare `"decision": "pending"` imports as `Decision("pending", found, "")` with an empty history.

The state set is `pending`, `accepted`, `act` and `declined`. The prototype used `accepted` and
`pending`, and both carry over unchanged.

### 7. Files and names

| Path | What |
|---|---|
| `<env root>/findings/findings.json` | The ledger. Schema version `1`, JSON with two-space indent, UTF-8 not escaped, keys in a fixed order, final newline. |
| `<env root>/findings/data/` | The tables findings cite |
| `<env root>/reports/findings-client.<lang>.md` | The client report. Overwritten on each write, because it is a rendering, not a record; the ledger is the record. |
| `<env root>/reports/findings-extended.<lang>.md` | The extended report, likewise |

File names are English, like every generated file. Only the report's contents follow the chosen language.

`MigrationEnv` gains `findings_dir`, `findings_ledger` and `findings_data_dir`.

### 8. Surface

Non-interactive commands, which write nothing:

```
odoo-dwg migrate findings list     --source 12 --target 18
odoo-dwg migrate findings show ID  --source 12 --target 18
odoo-dwg migrate findings validate --source 12 --target 18
odoo-dwg migrate findings report   --source 12 --target 18 --kind client|extended --report-lang en|es
odoo-dwg migrate findings links    --source 12 --target 18
```

The report language option is `--report-lang`, not `--lang`. `--lang` is already the UI language, and the
whole point of decision 4 is that the two are independent.

Menu actions, under Migration → Findings, each previewing the ledger or report file it writes and asking
for confirmation:
- start a ledger;
- add findings from a JSON file;
- record a decision;
- set a phase's state;
- withdraw a finding;
- write the reports.

The ledger is rewritten whole, through `write_text_file_command`, so the preview shows the resulting file.

### 9. The link check is a system call, run only on request

`system.url_status(url, timeout)` issues a stdlib `urllib` `HEAD` request and falls back to `GET` when
`HEAD` gets a 405. It returns the final status after redirects, or the error. Tests cover the walk
against a stubbed status function, never the network.

The `links` command walks only the **reference** links:
- the context;
- the client texts;
- table titles and notes.

It never walks evidence, summaries or queries. The first version walked every string in the ledger, and
its first real run sent a `HEAD` request to the ESR client's production server, whose `web.base.url` is
recorded as evidence. A URL that describes the client's system is not a link to check. A test now pins
that exclusion.

## Risks / Trade-offs

- **The ledger is hand-editable JSON, and a hand edit can break it.** → `validate` names every problem;
  every command and action parses through the same validator, so a broken ledger is refused, never
  half-read.
- **Per-language client text doubles the writing for a bilingual client.** → Only the languages actually
  rendered need text, and a missing language fails loudly at render time rather than shipping a gap.
- **Tables relabel headers but not values**, so a Spanish client table needs Spanish values from its
  producer. → That is where the vocabulary lives anyway: the intake knows what `not_sent` means, the
  renderer should not.

## Migration Plan

1. Implement and test.
2. On the host, convert the ESR prototype, outside the repository:
   - tag the client text `es`;
   - wrap decisions;
   - turn the bespoke tables into `tables` entries over the existing TSVs, writing client-ready Spanish
     tables where the prototype translated values.
3. Validate the converted ledger.
4. Render both reports in Spanish and compare them against the prototype's output. Differences must be
   explained, not silent.
5. Retire `generar_informes.py` and point the environment's `LEEME.md` at the new commands.

Rolling back means keeping the prototype files, which are untouched until the last step.
