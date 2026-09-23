"""The findings ledger of a migration environment, and the reports rendered from it.

A migration finds things — a module that sends invoices to the tax agency, crons
that fire the moment Odoo starts, mail that has not left for years. Each one is
recorded once, in ``findings/findings.json``, with the evidence behind it and the
query that re-derives it, and the client's decision on it. The reports are
renderings of that ledger and nothing else, so a report is never edited by hand:
it is rendered again.

Pure: parsing, validation, operations and rendering take and return values. The
files are read and written by the workflow.

Prose meant for a reader — a phase title, a received item, a finding's client
text — is a *localized text*: either a plain string, used as is in every
language, or ``{"en": ..., "es": ...}``. A report in a language a text lacks is
refused and the missing text named, rather than shown in another language.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import date

from .i18n import translate

SCHEMA_VERSION = 1
LANGUAGES = ("en", "es")
SEVERITIES = ("critical", "high", "medium", "low", "info")
AUDIENCES = ("client", "internal")
DECISIONS = ("pending", "accepted", "act", "declined")
PHASE_STATES = ("pending", "in-progress", "done")

_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TABLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.tsv$")
_URL_RE = re.compile(r"https?://[^\s)\]>|\"']+")

#: Where the client report places a finding, by its severity (or its client level).
_GROUP_OF = {"critical": "Important", "high": "Important", "medium": "Worth knowing",
             "low": "Worth knowing", "info": "For your information"}
_GROUPS = ("Important", "Worth knowing", "For your information")
_STATE_LABEL = {"pending": "Pending", "in-progress": "In progress", "done": "Done"}
_STATE_MARK = {"pending": "⏳", "in-progress": "🔄", "done": "✅"}
_DECISION_LABEL = {"pending": "Pending", "accepted": "Accepted", "act": "Act on it",
                   "declined": "Declined"}

Text = str | dict[str, str]


class LedgerError(ValueError):
    """A ledger, or an operation on one, that cannot be accepted — with every reason."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


# --- the data --------------------------------------------------------------------

@dataclass(frozen=True)
class Decision:
    state: str
    date: str
    note: str = ""


@dataclass(frozen=True)
class TableRef:
    """A table from ``findings/data/`` a finding shows, relabelled per language."""

    file: str
    audience: str
    title: Text = ""
    columns: dict[str, list[str]] = field(default_factory=dict)
    note: Text = ""


@dataclass(frozen=True)
class Finding:
    id: str
    found: str
    phase: str
    severity: str
    category: str
    audience: str
    subject: str
    summary: str
    evidence: object
    query: str
    action: str
    decision: Decision
    history: tuple[Decision, ...] = ()
    client: dict[str, dict[str, str]] = field(default_factory=dict)
    tables: tuple[TableRef, ...] = ()


@dataclass(frozen=True)
class Correction:
    date: str
    withdrawn: str
    reason: str
    finding: Finding | None = None


@dataclass(frozen=True)
class Phase:
    id: str
    title: Text
    state: str


@dataclass(frozen=True)
class Ledger:
    client_name: str
    database: str
    source_version: str
    target_version: str
    reference_database: str
    note: str = ""
    context: dict = field(default_factory=dict)
    phases: tuple[Phase, ...] = ()
    findings: tuple[Finding, ...] = ()
    corrections: tuple[Correction, ...] = ()


# --- parsing and validation --------------------------------------------------------

def _text_problems(value: object, where: str) -> list[str]:
    if isinstance(value, str):
        return []
    if isinstance(value, dict) and value and all(
        k in LANGUAGES and isinstance(v, str) for k, v in value.items()
    ):
        return []
    return [f"{where}: expected a string or {{language: string}} with languages {LANGUAGES}"]


def _date_problems(value: object, where: str) -> list[str]:
    if isinstance(value, str) and _DATE_RE.fullmatch(value):
        try:
            date.fromisoformat(value)
            return []
        except ValueError:
            pass
    return [f"{where}: expected a date YYYY-MM-DD, got {value!r}"]


def _choice_problems(value: object, allowed: tuple[str, ...], where: str) -> list[str]:
    return [] if value in allowed else [f"{where}: {value!r} is not one of {', '.join(allowed)}"]


def _decision(raw: object, where: str, problems: list[str]) -> Decision:
    if not isinstance(raw, dict):
        problems.append(f"{where}: expected {{state, date, note}}")
        return Decision("pending", "1970-01-01")
    problems += _choice_problems(raw.get("state"), DECISIONS, f"{where}.state")
    problems += _date_problems(raw.get("date"), f"{where}.date")
    return Decision(str(raw.get("state", "")), str(raw.get("date", "")), str(raw.get("note", "")))


def _table(raw: object, where: str, problems: list[str]) -> TableRef:
    if not isinstance(raw, dict):
        problems.append(f"{where}: expected {{file, audience, title, columns}}")
        return TableRef("", "internal")
    name = raw.get("file")
    if not (isinstance(name, str) and _TABLE_RE.fullmatch(name)):
        problems.append(f"{where}.file: expected a .tsv file name in findings/data, got {name!r}")
    problems += _choice_problems(raw.get("audience"), AUDIENCES, f"{where}.audience")
    title = raw.get("title", "")
    problems += _text_problems(title, f"{where}.title")
    note = raw.get("note", "")
    problems += _text_problems(note, f"{where}.note")
    columns = raw.get("columns", {})
    if not (isinstance(columns, dict) and all(
        k in LANGUAGES and isinstance(v, list) and all(isinstance(c, str) for c in v)
        for k, v in columns.items()
    )):
        problems.append(f"{where}.columns: expected {{language: [column, ...]}}")
        columns = {}
    return TableRef(str(name or ""), str(raw.get("audience", "")), title, dict(columns), note)


def _required_str(raw: dict, key: str, where: str, problems: list[str]) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{where}.{key}: required")
        return ""
    return value


def parse_finding(raw: object, where: str, problems: list[str]) -> Finding | None:
    """One finding from its JSON form; every problem is appended, none raised."""
    if not isinstance(raw, dict):
        problems.append(f"{where}: expected an object")
        return None
    fid = raw.get("id")
    if not (isinstance(fid, str) and _ID_RE.fullmatch(fid)):
        problems.append(f"{where}.id: expected lower-case kebab-case, got {fid!r}")
    where = f"finding {fid}" if isinstance(fid, str) else where
    problems += _date_problems(raw.get("found"), f"{where}.found")
    problems += _choice_problems(raw.get("severity"), SEVERITIES, f"{where}.severity")
    problems += _choice_problems(raw.get("audience"), AUDIENCES, f"{where}.audience")
    text = {key: _required_str(raw, key, where, problems)
            for key in ("phase", "category", "subject", "summary", "query", "action")}
    evidence = raw.get("evidence")
    if evidence in (None, "", {}, []):
        problems.append(f"{where}.evidence: required")
    decision = _decision(raw.get("decision"), f"{where}.decision", problems)
    history = tuple(_decision(item, f"{where}.history[{i}]", problems)
                    for i, item in enumerate(raw.get("history", []) or []))
    client = raw.get("client", {}) or {}
    if not isinstance(client, dict):
        problems.append(f"{where}.client: expected {{language: {{title, text, question}}}}")
        client = {}
    for lang, block in client.items():
        if lang not in LANGUAGES:
            problems.append(f"{where}.client: unknown language {lang!r}")
            continue
        if not (isinstance(block, dict) and isinstance(block.get("title"), str)
                and isinstance(block.get("text"), str)):
            problems.append(f"{where}.client.{lang}: expected title and text")
            continue
        if "level" in block:
            problems += _choice_problems(block["level"], SEVERITIES, f"{where}.client.{lang}.level")
    tables = tuple(_table(item, f"{where}.tables[{i}]", problems)
                   for i, item in enumerate(raw.get("tables", []) or []))
    return Finding(
        id=str(fid or ""), found=str(raw.get("found", "")), severity=str(raw.get("severity", "")),
        audience=str(raw.get("audience", "")), evidence=evidence, decision=decision,
        history=history, client={k: dict(v) for k, v in client.items() if isinstance(v, dict)},
        tables=tables, **text,
    )


def _context_problems(context: object) -> list[str]:
    if not isinstance(context, dict):
        return ["context: expected an object"]
    problems: list[str] = []
    shapes = {"received": ("item", "detail", "date"), "versions": ("what", "value", "link"),
              "sources": ("origin", "link"), "references": ("what", "link")}
    handling = context.get("data_handling", [])
    if not isinstance(handling, list):
        problems.append("context.data_handling: expected a list")
    else:
        for i, line in enumerate(handling):
            problems += _text_problems(line, f"context.data_handling[{i}]")
    for key, fields in shapes.items():
        rows = context.get(key, [])
        if not isinstance(rows, list):
            problems.append(f"context.{key}: expected a list")
            continue
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                problems.append(f"context.{key}[{i}]: expected an object")
                continue
            for name in fields:
                if name == "link":
                    if not isinstance(row.get("link", ""), str):
                        problems.append(f"context.{key}[{i}].link: expected a string")
                else:
                    problems += _text_problems(row.get(name), f"context.{key}[{i}].{name}")
    return problems


def _uniqueness_problems(ledger: Ledger) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for finding in ledger.findings:
        if finding.id in seen:
            problems.append(f"finding {finding.id}: duplicate id")
        seen.add(finding.id)
    for correction in ledger.corrections:
        if correction.withdrawn in seen:
            problems.append(f"finding {correction.withdrawn}: id belongs to a withdrawn finding")
        seen.add(correction.withdrawn)
    phase_ids = [p.id for p in ledger.phases]
    for pid in sorted({p for p in phase_ids if phase_ids.count(p) > 1}):
        problems.append(f"phase {pid}: duplicate id")
    return problems


def parse_ledger(text: str) -> Ledger:
    """A ledger from its JSON text; raises ``LedgerError`` with every problem found."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise LedgerError([f"not valid JSON: {error}"]) from None
    if not isinstance(raw, dict):
        raise LedgerError(["expected a JSON object"])
    if raw.get("schema") != SCHEMA_VERSION:
        raise LedgerError([
            f"schema version {raw.get('schema')!r} is not one this tool reads "
            f"(it reads {SCHEMA_VERSION})"
        ])
    problems: list[str] = []
    head = {key: _required_str(raw, key, "ledger", problems) for key in (
        "client_name", "database", "source_version", "target_version", "reference_database")}
    problems += _context_problems(raw.get("context", {}))
    phases: list[Phase] = []
    for i, item in enumerate(raw.get("phases", []) or []):
        if not isinstance(item, dict):
            problems.append(f"phases[{i}]: expected an object")
            continue
        if not (isinstance(item.get("id"), str) and _ID_RE.fullmatch(item["id"])):
            problems.append(f"phases[{i}].id: expected lower-case kebab-case")
        problems += _text_problems(item.get("title"), f"phases[{i}].title")
        problems += _choice_problems(item.get("state"), PHASE_STATES, f"phases[{i}].state")
        phases.append(Phase(str(item.get("id", "")), item.get("title", ""),
                            str(item.get("state", ""))))
    findings = [parse_finding(item, f"findings[{i}]", problems)
                for i, item in enumerate(raw.get("findings", []) or [])]
    corrections: list[Correction] = []
    for i, item in enumerate(raw.get("corrections", []) or []):
        where = f"corrections[{i}]"
        if not isinstance(item, dict):
            problems.append(f"{where}: expected an object")
            continue
        problems += _date_problems(item.get("date"), f"{where}.date")
        withdrawn = _required_str(item, "withdrawn", where, problems)
        reason = _required_str(item, "reason", where, problems)
        kept = item.get("finding")
        finding = parse_finding(kept, f"{where}.finding", problems) if kept is not None else None
        corrections.append(Correction(str(item.get("date", "")), withdrawn, reason, finding))
    ledger = Ledger(
        note=str(raw.get("note", "")), context=dict(raw.get("context", {}) or {}),
        phases=tuple(phases), findings=tuple(f for f in findings if f is not None),
        corrections=tuple(corrections), **head,
    )
    problems += _uniqueness_problems(ledger)
    if problems:
        raise LedgerError(problems)
    return ledger


def parse_findings(text: str) -> list[Finding]:
    """Findings to add, from a JSON list (or ``{"findings": [...]}``)."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise LedgerError([f"not valid JSON: {error}"]) from None
    if isinstance(raw, dict):
        raw = raw.get("findings")
    if not isinstance(raw, list) or not raw:
        raise LedgerError(["expected a non-empty list of findings"])
    problems: list[str] = []
    parsed = [parse_finding(item, f"findings[{i}]", problems) for i, item in enumerate(raw)]
    if problems:
        raise LedgerError(problems)
    return [f for f in parsed if f is not None]


# --- serialising -------------------------------------------------------------------

def _decision_json(d: Decision) -> dict:
    return {"state": d.state, "date": d.date, "note": d.note}


def _table_json(ref: TableRef) -> dict:
    out: dict = {"file": ref.file, "audience": ref.audience}
    if ref.title:
        out["title"] = ref.title
    if ref.columns:
        out["columns"] = ref.columns
    if ref.note:
        out["note"] = ref.note
    return out


def finding_json(f: Finding) -> dict:
    out: dict = {
        "id": f.id, "found": f.found, "phase": f.phase, "severity": f.severity,
        "category": f.category, "audience": f.audience, "subject": f.subject,
        "summary": f.summary, "evidence": f.evidence, "query": f.query, "action": f.action,
        "decision": _decision_json(f.decision),
    }
    if f.history:
        out["history"] = [_decision_json(d) for d in f.history]
    if f.client:
        out["client"] = f.client
    if f.tables:
        out["tables"] = [_table_json(t) for t in f.tables]
    return out


def dump_ledger(ledger: Ledger) -> str:
    """The ledger's JSON text: fixed key order, two-space indent, final newline."""
    corrections = []
    for c in ledger.corrections:
        item: dict = {"date": c.date, "withdrawn": c.withdrawn, "reason": c.reason}
        if c.finding is not None:
            item["finding"] = finding_json(c.finding)
        corrections.append(item)
    raw = {
        "schema": SCHEMA_VERSION,
        "client_name": ledger.client_name, "database": ledger.database,
        "source_version": ledger.source_version, "target_version": ledger.target_version,
        "reference_database": ledger.reference_database, "note": ledger.note,
        "context": ledger.context,
        "phases": [{"id": p.id, "title": p.title, "state": p.state} for p in ledger.phases],
        "findings": [finding_json(f) for f in ledger.findings],
        "corrections": corrections,
    }
    return json.dumps(raw, indent=2, ensure_ascii=False) + "\n"


# --- operations --------------------------------------------------------------------

#: The phases a new ledger starts with; the operator edits or extends them.
DEFAULT_PHASES = (
    Phase("intake", {"en": "Restore the client's copy and read it", "es":
                     "Restaurar la copia del cliente y leerla"}, "pending"),
    Phase("outbound-inventory", {"en": "Find what can send information outside", "es":
                                 "Revisar qué puede enviar información al exterior"}, "pending"),
    Phase("module-classification", {"en": "Classify the modules and their fate", "es":
                                    "Clasificar los módulos y su futuro"}, "pending"),
    Phase("neutralise", {"en": "Prepare test copies that cannot send anything", "es":
                         "Preparar las copias de prueba sin riesgo de envíos"}, "pending"),
    Phase("rehearsal", {"en": "Rehearse the migration", "es": "Ensayos de la migración"},
          "pending"),
    Phase("custom-port", {"en": "Port the custom modules", "es":
                          "Adaptar los desarrollos a medida"}, "pending"),
    Phase("cutover", {"en": "Final migration", "es": "Migración definitiva"}, "pending"),
)


#: What a new ledger tells the client about their data. It is the ledger's to say,
#: not the renderer's: a promise that test copies send nothing is only true once
#: they have been neutralised, and the operator edits it to match.
DEFAULT_DATA_HANDLING = (
    {"en": "We work on a copy; the production database is not touched.",
     "es": "Trabajamos sobre una copia; la base de datos de producción no se toca."},
)


def new_ledger(client_name: str, database: str, source: str, target: str,
               reference_database: str) -> Ledger:
    ledger = Ledger(client_name, database, source, target, reference_database,
                    context={"received": [], "versions": [], "sources": [], "references": [],
                             "data_handling": list(DEFAULT_DATA_HANDLING)},
                    phases=DEFAULT_PHASES)
    parse_ledger(dump_ledger(ledger))  # a new ledger is a valid one, or nothing is written
    return ledger


def _checked(ledger: Ledger) -> Ledger:
    """Every operation's result goes through the same validation as a ledger read from disk."""
    return parse_ledger(dump_ledger(ledger))


def add_findings(ledger: Ledger, new: list[Finding]) -> Ledger:
    return _checked(replace(ledger, findings=ledger.findings + tuple(new)))


def _index(ledger: Ledger, finding_id: str) -> int:
    for i, f in enumerate(ledger.findings):
        if f.id == finding_id:
            return i
    raise LedgerError([f"finding {finding_id}: not in the ledger"])


def decide(ledger: Ledger, finding_id: str, state: str, on: str, note: str = "") -> Ledger:
    """Record a decision; the one it replaces moves to the finding's history."""
    i = _index(ledger, finding_id)
    old = ledger.findings[i]
    updated = replace(old, decision=Decision(state, on, note), history=old.history + (old.decision,))
    return _checked(replace(ledger, findings=ledger.findings[:i] + (updated,)
                            + ledger.findings[i + 1:]))


def withdraw(ledger: Ledger, finding_id: str, on: str, reason: str) -> Ledger:
    """Move a finding to the corrections log. Its id stays taken."""
    if not reason.strip():
        raise LedgerError([f"finding {finding_id}: a withdrawal needs its reason"])
    i = _index(ledger, finding_id)
    correction = Correction(on, finding_id, reason, ledger.findings[i])
    return _checked(replace(ledger, findings=ledger.findings[:i] + ledger.findings[i + 1:],
                            corrections=ledger.corrections + (correction,)))


def set_phase(ledger: Ledger, phase_id: str, state: str) -> Ledger:
    if phase_id not in {p.id for p in ledger.phases}:
        raise LedgerError([f"phase {phase_id}: not in the ledger"])
    phases = tuple(replace(p, state=state) if p.id == phase_id else p for p in ledger.phases)
    return _checked(replace(ledger, phases=phases))


def pending(ledger: Ledger) -> list[Finding]:
    return [f for f in ledger.findings if f.decision.state == "pending"]


def ledger_urls(ledger: Ledger) -> list[tuple[str, str]]:
    """``(where, url)`` for every *reference* link, in document order.

    Only what the ledger cites for a reader: the context, the client texts, and
    the tables' titles and notes. Never a finding's evidence, summary or query —
    a URL there is a fact about the client's system (its production
    ``web.base.url``, say), and requesting it would reach that system: the first
    run of this check did, against a client's production server."""
    found: list[tuple[str, str]] = []

    def walk(value: object, where: str) -> None:
        if isinstance(value, str):
            found.extend((where, url.rstrip(".,;:")) for url in _URL_RE.findall(value))
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{where}.{key}" if where else str(key))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                walk(item, f"{where}[{i}]")

    raw = json.loads(dump_ledger(ledger))
    walk(raw["context"], "context")
    for i, finding in enumerate(raw["findings"]):
        walk(finding.get("client", {}), f"findings[{i}].client")
        for j, table in enumerate(finding.get("tables", [])):
            walk({k: table[k] for k in ("title", "note") if k in table},
                 f"findings[{i}].tables[{j}]")
    return found


# --- rendering ---------------------------------------------------------------------

def parse_tsv(text: str) -> list[list[str]]:
    """A table from ``findings/data/``: tab-separated, first row is the header."""
    return [line.split("\t") for line in text.splitlines() if line.strip()]


def _cell(value: object) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def _bare(url: str) -> str:
    """A link's label: the URL without its scheme or trailing slash."""
    return re.sub(r"^https?://", "", url).rstrip("/")


def _md_table(head: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(_cell(h) for h in head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return out + [""]


class _Render:
    """What a rendering needs, and the problems it met on the way."""

    def __init__(self, ledger: Ledger, tables: dict[str, list[list[str]]], lang: str,
                 today: date):
        if lang not in LANGUAGES:
            raise LedgerError([f"report language {lang!r} is not one of {', '.join(LANGUAGES)}"])
        self.ledger, self.tables, self.lang, self.today = ledger, tables, lang, today
        self.problems: list[str] = []

    def t(self, text: str) -> str:
        return translate(text, self.lang)

    def text(self, value: Text, where: str) -> str:
        if isinstance(value, str):
            return value
        if self.lang in value:
            return value[self.lang]
        self.problems.append(f"{where}: no {self.lang} text")
        return ""

    def date(self) -> str:
        return self.today.strftime("%d/%m/%Y") if self.lang == "es" else self.today.isoformat()

    def link(self, label: str, url: str) -> str:
        return f"[{label}]({url})" if url else label

    def table(self, ref: TableRef, where: str) -> list[str]:
        rows = self.tables.get(ref.file)
        if not rows:
            self.problems.append(f"{where}: table findings/data/{ref.file} is missing or has "
                                 "no header row")
            return []
        head = ref.columns.get(self.lang, rows[0])
        if len(head) != len(rows[0]):
            self.problems.append(f"{where}: {len(head)} {self.lang} column labels for "
                                 f"{len(rows[0])} columns")
            return []
        out = []
        title = self.text(ref.title, f"{where}.title") if ref.title else ""
        if title:
            out += [f"**{title}**", ""]
        out += _md_table(head, rows[1:])
        note = self.text(ref.note, f"{where}.note") if ref.note else ""
        return out + ([note, ""] if note else [])

    def finish(self, lines: list[str]) -> str:
        if self.problems:
            raise LedgerError(self.problems)
        return "\n".join(lines).rstrip("\n") + "\n"


def _head(r: _Render, title: str) -> list[str]:
    led = r.ledger
    return [f"# {title}", "",
            f"**{led.client_name}** · " + r.t("report as of {}").format(r.date()), "",
            "> " + r.t("Generated from the findings ledger. Do not edit it: render it again."),
            ""]


def _phases(r: _Render) -> list[str]:
    rows = [[r.text(p.title, f"phase {p.id}.title"),
             f"{_STATE_MARK[p.state]} {r.t(_STATE_LABEL[p.state])}"]
            for p in r.ledger.phases]
    return _md_table([r.t("Phase"), r.t("State")], rows) if rows else []


def _received(r: _Render) -> list[str]:
    rows = [[r.text(x["item"], f"context.received[{i}].item"),
             r.text(x["detail"], f"context.received[{i}].detail"), r.text(x["date"], "")]
            for i, x in enumerate(r.ledger.context.get("received", []))]
    return _md_table([r.t("What"), r.t("Detail"), r.t("Date")], rows) if rows else []


def _versions(r: _Render) -> list[str]:
    rows = [[r.text(x["what"], f"context.versions[{i}].what"),
             r.text(x["value"], f"context.versions[{i}].value"),
             r.link(r.t("link"), x.get("link", ""))]
            for i, x in enumerate(r.ledger.context.get("versions", []))]
    return _md_table(["", r.t("Version"), r.t("Reference")], rows) if rows else []


def _references(r: _Render) -> list[str]:
    context = r.ledger.context
    rows = [[r.text(x["origin"], f"context.sources[{i}].origin"),
             r.link(_bare(x["link"]), x["link"]) if x.get("link") else r.t("private repository")]
            for i, x in enumerate(context.get("sources", []))]
    rows += [[r.text(x["what"], f"context.references[{i}].what"),
              r.link(_bare(x["link"]), x["link"])]
             for i, x in enumerate(context.get("references", []))]
    if not rows:
        return []
    return ["## " + r.t("Reference links"), ""] + _md_table([r.t("What"), r.t("Where")], rows)


def _client_block(r: _Render, f: Finding) -> dict[str, str]:
    block = f.client.get(r.lang)
    if block is None:
        r.problems.append(f"finding {f.id}: no {r.lang} client text")
        return {"title": f.id, "text": "", "question": ""}
    return block


def render_client_report(ledger: Ledger, tables: dict[str, list[list[str]]], lang: str,
                         today: date) -> str:
    """The report for the client: plain, with tables and links, no internal matter."""
    r = _Render(ledger, tables, lang, today)
    shown = [f for f in ledger.findings if f.audience == "client"]
    blocks = {f.id: _client_block(r, f) for f in shown}
    title = r.t("Migration of Odoo {} to {}").format(
        ledger.source_version.split(".")[0], ledger.target_version.split(".")[0])
    out = _head(r, title)
    out += ["## " + r.t("Where we are"), ""] + _phases(r)
    out += ["## " + r.t("What we analysed"), ""] + _received(r)
    out += ["## " + r.t("Versions"), ""] + _versions(r)
    questions = [f for f in shown if f.decision.state == "pending" and blocks[f.id].get("question")]
    if questions:
        out += ["## " + r.t("What we need you to confirm"), ""]
        out += [f"{i}. **{blocks[f.id]['title']}.** {blocks[f.id]['question']}"
                for i, f in enumerate(questions, 1)]
        out += [""]
    out += ["## " + r.t("What we found"), ""]
    for group in _GROUPS:
        items = [f for f in shown
                 if _GROUP_OF[blocks[f.id].get("level", f.severity)] == group]
        if not items:
            continue
        out += ["### " + r.t(group), ""]
        for f in items:
            out += [f"#### {blocks[f.id]['title']}", "", blocks[f.id]["text"], ""]
            for i, ref in enumerate(f.tables):
                if ref.audience == "client":
                    out += r.table(ref, f"finding {f.id}.tables[{i}]")
    handling = [r.text(x, f"context.data_handling[{i}]")
                for i, x in enumerate(ledger.context.get("data_handling", []))]
    if handling:
        out += ["## " + r.t("How we handle your data"), ""]
        out += [f"- {line}" for line in handling] + [""]
    out += _references(r)
    return r.finish(out)


def _decision_line(r: _Render, d: Decision) -> str:
    note = f" — {d.note}" if d.note else ""
    return f"{r.t(_DECISION_LABEL[d.state])} ({d.date}){note}"


def _finding_full(r: _Render, f: Finding, level: str) -> list[str]:
    out = [f"{level} {f.id}", "",
           f"- **{r.t('Severity')}:** {f.severity} · **{r.t('Category')}:** {f.category} · "
           f"**{r.t('Audience')}:** {f.audience} · **{r.t('Phase')}:** {f.phase} · "
           f"**{r.t('Found')}:** {f.found}",
           f"- **{r.t('About')}:** {f.subject}", "", f.summary, ""]
    block = f.client.get(r.lang)
    if block:
        out += [f"> **{r.t('For the client')} — {block['title']}.** {block['text']}"]
        if block.get("question"):
            out += [">", f"> **{r.t('Question')}:** {block['question']}"]
        out += [""]
    for i, ref in enumerate(f.tables):
        out += r.table(ref, f"finding {f.id}.tables[{i}]")
    out += [f"**{r.t('Evidence')}**", "", "```json",
            json.dumps(f.evidence, indent=2, ensure_ascii=False), "```", "",
            f"**{r.t('How to check it again')}:** `{f.query}`", "",
            f"**{r.t('Proposed action')}:** {f.action}", "",
            f"**{r.t('Decision')}:** {_decision_line(r, f.decision)}", ""]
    if f.history:
        out += [f"**{r.t('Earlier decisions')}:**", ""]
        out += [f"- {_decision_line(r, d)}" for d in f.history] + [""]
    return out


def render_extended_report(ledger: Ledger, tables: dict[str, list[list[str]]], lang: str,
                           today: date) -> str:
    """Everything, with the evidence and how to check it, and the corrections."""
    r = _Render(ledger, tables, lang, today)
    title = r.t("Extended report — {} {} → {}").format(
        ledger.database, ledger.source_version, ledger.target_version)
    out = _head(r, title)
    out += [r.t("Reference database (never modified): {}").format(
        f"`{ledger.reference_database}`"), ""]
    if ledger.note:
        out += [ledger.note, ""]
    out += ["## " + r.t("Phases"), ""] + _phases(r)
    out += ["## " + r.t("What was analysed"), ""] + _received(r)
    out += ["## " + r.t("Versions"), ""] + _versions(r)
    out += ["## " + r.t("Summary of findings"), ""]
    out += _md_table(
        [r.t("Id"), r.t("Severity"), r.t("Category"), r.t("Audience"), r.t("Decision")],
        [[f"[{f.id}](#{f.id})", f.severity, f.category, f.audience,
          r.t(_DECISION_LABEL[f.decision.state])] for f in ledger.findings])
    for f in ledger.findings:
        out += _finding_full(r, f, "##")
    if ledger.corrections:
        out += ["## " + r.t("Corrections"), ""]
        out += _md_table([r.t("Date"), r.t("Withdrawn"), r.t("Reason")],
                         [[c.date, c.withdrawn, c.reason] for c in ledger.corrections])
    out += _references(r)
    return r.finish(out)
