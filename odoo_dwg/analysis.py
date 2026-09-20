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

# A line's names, as maximal runs of word and dot characters — the shape both of
# the scan's word-boundary rules are decided from.
_DOTTED_RE = re.compile(r"[\w.]+")


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
    wanted = [
        record
        for record in records
        if not (record.kind == "removed_field" and record.name in GENERIC_FIELD_NAMES)
    ]
    # The names are looked *up*, not searched for one by one. One analysis step
    # carries tens of thousands of records and a module's source was scanned once
    # against each of them — minutes per module per step, and in the ordinary case
    # (a module inheriting a core model, so every record's model test passes and
    # no field name matches) minutes to produce nothing at all. Reading each line
    # once into the names it contains makes the cost the source's size, not the
    # product of the two.
    #
    # The two token shapes are the two word-boundary rules this scan had. A model
    # name must not match inside a longer dotted name, so it is looked up as a
    # whole `[\w.]+` run. A field matches inside one — `<model>.<field>` is the
    # normal usage — so it is looked up among a run's dot-separated pieces, of as
    # many components as the longest field name has (one, unless an analysis file
    # ever names a dotted field).
    models = {record.model for record in wanted if record.kind == "removed_field"}
    pieces = max(
        (record.name.count(".") + 1 for record in wanted if record.kind == "removed_field"),
        default=1,
    )
    findings: list[Finding] = []
    if not wanted:
        # Nothing to look up, so nothing to index: a step whose OpenUpgrade
        # clone is absent has no records, and indexing a 14 MB module for it
        # cost seconds and a hundred megabytes to return an empty list.
        return findings
    for path, text in files:
        present = {model for model in models if model in text}
        words: dict[str, list[int]] = {}
        dotted: dict[str, list[int]] = {}
        for line_number, line in enumerate(text.splitlines(), start=1):
            runs = set(_DOTTED_RE.findall(line))
            in_line: set[str] = set()
            for run in runs:
                parts = run.split(".")
                for first in range(len(parts)):
                    for last in range(first + 1, min(first + pieces, len(parts)) + 1):
                        in_line.add(".".join(parts[first:last]))
            for token in in_line:
                words.setdefault(token, []).append(line_number)
            for token in runs:
                dotted.setdefault(token, []).append(line_number)
        # Record order, then line order — the order the scan has always reported.
        for record in wanted:
            if record.kind == "removed_field":
                if record.model not in present:
                    continue
                hits = words.get(record.name, ())
            else:
                hits = dotted.get(record.name, ())
            findings.extend(Finding(path, line_number, record) for line_number in hits)
    return findings


# The classes of change a chain does to a module, and what each one costs the
# module that depended on it. Harvested from the 2341 analysis files of
# OpenUpgrade 14.0-19.0, not invented: every pattern below is a status string
# those files actually carry, and the counts are in the change's design note.
#
# "Loud" means the module stops loading and the step fails, which the driver
# already catches. "Quiet" means it keeps loading and something is gone.
CHANGE_CLASSES: dict[str, tuple[str, str]] = {
    "removed_field": ("loud", "the field is gone"),
    "removed_model": ("loud", "the model is gone"),
    "renamed_model": ("quiet", "the model answers to another name"),
    # Module fates come from apriori.py, not from an analysis file; they are
    # classes of the same kind and are checked the same way after a step.
    "renamed_module": ("quiet", "the module answers to another name"),
    "merged_module": ("quiet", "the module was absorbed into another"),
    "moved_field": ("quiet", "the field belongs to another module now"),
    "unstored_field": ("quiet", "the field is no longer stored — its column goes"),
    "stored_field": ("quiet", "the field is stored now, and starts empty"),
    "unrelated_field": ("quiet", "the field is no longer related"),
    "related_field": ("quiet", "the field is related now"),
    "function_field": ("quiet", "the field is computed now"),
    "unfunction_field": ("quiet", "the field is no longer computed"),
    "selection_changed": ("quiet", "a selection key it held is no longer accepted"),
    "company_dependent": ("quiet", "the field is company-dependent now"),
}

# One pattern per status, and no status matches two: checked against the whole
# vocabulary by tools/verify_migration_tester.py, so a pattern added later cannot
# quietly start claiming another's lines. The negatives are spelled out in full
# ("not a function anymore", not "function") for that reason.
_FIELD_STATUS_CLASSES: tuple[tuple[str, str], ...] = (
    ("not stored anymore", "unstored_field"),
    ("not related anymore", "unrelated_field"),
    ("not a function anymore", "unfunction_field"),
    ("now a function", "function_field"),
    ("is now stored", "stored_field"),
    ("now related", "related_field"),
    ("module is now", "moved_field"),
    ("previously in module", "moved_field"),
    ("selection_keys is now", "selection_changed"),
    ("company dependent", "company_dependent"),
)
_RENAMED_MODEL_RE = re.compile(r"^obsolete model (?P<model>[\w.]+) \(renamed to (?P<to>[\w.]+)\)")


@dataclass(frozen=True)
class ChangeRecord:
    """One change of any class, as an analysis file states it.

    ``detail`` is the file's own words, kept verbatim: a probe names the record
    it came from, and paraphrasing it would make that claim unverifiable.
    """

    module: str
    model: str
    field: str       # "" for a model-level change
    kind: str
    detail: str


def harvest_changes(text: str) -> list[ChangeRecord]:
    """Every class of change an analysis file states, not only the breaking ones.

    ``parse_analysis`` deliberately keeps to what breaks a *reference* — that is
    what the staging scan searches source for. This is the whole vocabulary,
    because the quiet classes are exactly the ones nothing else reports.
    """
    changes: list[ChangeRecord] = []
    module = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        section = _SECTION_RE.match(line)
        if section:
            module = section.group("module")
            continue
        renamed = _RENAMED_MODEL_RE.match(line)
        if renamed:
            changes.append(
                ChangeRecord(module, renamed.group("model"), "", "renamed_model", line)
            )
            continue
        obsolete = _OBSOLETE_MODEL_RE.match(line)
        if obsolete:
            changes.append(
                ChangeRecord(module, obsolete.group("model"), "", "removed_model", line)
            )
            continue
        row = _FIELD_ROW_RE.match(line)
        if not row:
            continue
        status = row.group("status")
        kind = "removed_field" if status.split()[0] == "DEL" else ""
        if not kind:
            kind = next(
                (name for token, name in _FIELD_STATUS_CLASSES if token in status), ""
            )
        if kind:
            changes.append(
                ChangeRecord(
                    row.group("module"), row.group("model"), row.group("field"), kind, line
                )
            )
    return changes
