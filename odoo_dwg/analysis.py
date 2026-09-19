"""Pure parsing of OpenUpgrade ``upgrade_analysis.txt`` files and candidate
scanning of custom-module source (F3.2 staging).

Format anchored to the real files (verified against
``openupgrade_scripts/scripts/base/18.0.1.3/upgrade_analysis.txt`` on the 18.0
branch): section headers ``---Models in module 'X'---`` / ``---Fields in module
'X'---``; model lines like ``obsolete model ir.property [transient]``; field
rows ``module / model / field (type) : STATUS extras`` where the breaking
status is ``DEL``.

Everything here is standard library and pure — callers read the files and pass
text in, so tests run on fixture strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SECTION_RE = re.compile(r"^---(Models|Fields) in module '(?P<module>[\w.]+)'---$")
_OBSOLETE_MODEL_RE = re.compile(r"^obsolete model (?P<model>[\w.]+)")
_FIELD_ROW_RE = re.compile(
    r"^(?P<module>[\w.]+)\s*/\s*(?P<model>[\w.]+)\s*/\s*(?P<field>\w+)\s*\((?P<type>[\w.]*)\)\s*:\s*(?P<status>.+)$"
)

# Field names too generic to scan for — a bare occurrence of "name" or "state"
# in custom source says nothing. Their removals still appear in the report via
# the analysis records themselves; they are just not text-matched.
GENERIC_FIELD_NAMES = frozenset(
    {"name", "state", "type", "date", "user_id", "company_id", "partner_id",
     "active", "sequence", "code", "note", "value", "description", "display_name"}
)


@dataclass(frozen=True)
class AnalysisRecord:
    """One breaking change harvested from an analysis file."""

    module: str          # core module whose analysis declared it
    model: str
    kind: str            # "removed_model" | "removed_field"
    name: str            # the model name (removed_model) or field name


@dataclass(frozen=True)
class Finding:
    """A candidate occurrence of a breaking name in custom source."""

    path: str
    line: int
    record: AnalysisRecord


def parse_analysis(text: str) -> list[AnalysisRecord]:
    """Extract the *breaking* records: obsolete models and DEL fields. NEW/`now
    required`/selection changes are upgrade information, not broken references."""
    records: list[AnalysisRecord] = []
    module = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        section = _SECTION_RE.match(line)
        if section:
            module = section.group("module")
            continue
        obsolete = _OBSOLETE_MODEL_RE.match(line)
        if obsolete:
            records.append(
                AnalysisRecord(module, obsolete.group("model"), "removed_model",
                               obsolete.group("model"))
            )
            continue
        row = _FIELD_ROW_RE.match(line)
        if row and row.group("status").split()[0] == "DEL":
            records.append(
                AnalysisRecord(row.group("module"), row.group("model"),
                               "removed_field", row.group("field"))
            )
    return records


def scan_source(
    files: list[tuple[str, str]], records: list[AnalysisRecord]
) -> list[Finding]:
    """Word-boundary scan of (path, text) pairs for the breaking names.

    Candidates, not proof — a name match needs developer confirmation. To keep
    the noise floor sane: removed *fields* only match in files that also mention
    the owning model, and ultra-generic field names are skipped entirely (see
    ``GENERIC_FIELD_NAMES``)."""
    findings: list[Finding] = []
    # Compiled once per record, not once per (file x record) pair: a long chain
    # would otherwise thrash the module-level regex cache.
    patterns: list[tuple[AnalysisRecord, re.Pattern[str]]] = []
    for record in records:
        if record.kind == "removed_field":
            if record.name in GENERIC_FIELD_NAMES:
                continue
            # `record.doall` is the normal usage — a leading dot must match.
            patterns.append((record, re.compile(rf"(?<!\w){re.escape(record.name)}(?!\w)")))
        else:
            # Model names must not match inside longer dotted names.
            patterns.append((record, re.compile(rf"(?<![\w.]){re.escape(record.name)}(?![\w.])")))
    for path, text in files:
        for record, pattern in patterns:
            if record.kind == "removed_field" and record.model not in text:
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    findings.append(Finding(path, line_number, record))
    return findings
