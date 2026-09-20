"""The rehearsal tester: choosing probes from a chain's own sources, and reading
back what each step did to them.

Pure. The caller reads the analysis files and asks the database; everything here
takes text and rows and returns dataclasses, so the tests run on fixtures.

A probe is a *declaration*, never synthesized model code: a reference derived
wrongly from an analysis line fails on the source version rather than at the step
it is meant to test, which would destroy the rehearsal instead of measuring it.
``openspec/changes/archive/*-rehearse-with-a-module-that-breaks/design.md`` has
the reasoning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .analysis import CHANGE_CLASSES, ChangeRecord

#: The module the tester is generated as. Named for what it is, so an operator
#: who finds it installed somewhere knows at a glance.
TESTER_MODULE = "odwg_migration_tester"
#: Its one table, and the model behind it.
PROBE_MODEL = "odwg.migration.probe"
PROBE_TABLE = "odwg_migration_probe"

# Core modules a probe is preferred from. A chain's analysis files are dominated
# by localisation modules (`l10n_*` accounts for most XML records), and a tester
# depending on a Brazilian chart of accounts tests that chart, not the chain.
PREFERRED_MODULES = (
    "base", "account", "sale", "purchase", "stock", "product", "mail",
    "hr", "project", "crm", "point_of_sale", "mrp", "website",
)

# Names reaching a SQL string. The analysis files are not operator input, but
# they are input, and a model name is interpolated into the query that asks
# whether it survived.
_NAME_RE = re.compile(r"^[a-z_][\w.]*$", re.IGNORECASE)

#: Classes where the subject is *supposed* to be gone after its step. Everything
#: else is a change the subject is expected to survive — which is what makes its
#: disappearance a finding.
_EXPECTED_GONE = frozenset(
    {"removed_field", "removed_model", "renamed_model", "renamed_module", "merged_module"}
)
#: Classes whose subject is a *module*, looked up in `ir_module_module` rather
#: than in `ir_model`. Their records come from `apriori.py`.
_MODULE_CLASSES = frozenset({"renamed_module", "merged_module"})


@dataclass(frozen=True)
class Probe:
    """One declared expectation about one upstream subject."""

    name: str
    kind: str
    version: str     # the step whose analysis declared it
    model: str
    field: str       # "" for a model-level subject
    detail: str      # the analysis line, verbatim
    successor: str = ""   # what the sources say it becomes, where they say so

    @property
    def subject(self) -> str:
        return f"{self.model}/{self.field}" if self.field else self.model

    @property
    def subject_kind(self) -> str:
        """Which table answers for this subject. A module is not a model, and
        asking `ir_model` about one would report every module as gone."""
        if self.kind in _MODULE_CLASSES:
            return "module"
        return "field" if self.field else "model"

    @property
    def expected_gone(self) -> bool:
        return self.kind in _EXPECTED_GONE

    @property
    def loudness(self) -> str:
        return CHANGE_CLASSES[self.kind][0]


def _ranked(record: ChangeRecord) -> tuple:
    """Deterministic order, preferring a core module: the same chain must always
    produce the same probes, or two rehearsals cannot be compared."""
    try:
        preference = PREFERRED_MODULES.index(record.module)
    except ValueError:
        preference = len(PREFERRED_MODULES)
    return (preference, record.module, record.model, record.field)


def choose_probes(
    by_version: dict[str, list[ChangeRecord]], per_class: int = 1
) -> tuple[list[Probe], list[str]]:
    """One probe per class per step, and the classes this chain never exercises.

    The uncovered classes are returned rather than dropped: a class with no probe
    is not a class that passed.
    """
    probes: list[Probe] = []
    for version in sorted(by_version, key=_version_key):
        chosen: dict[str, int] = {}
        for record in sorted(by_version[version], key=_ranked):
            if record.kind not in CHANGE_CLASSES:
                continue
            if not _NAME_RE.match(record.model) or (record.field and not record.field.isidentifier()):
                continue
            if chosen.get(record.kind, 0) >= per_class:
                continue
            chosen[record.kind] = chosen.get(record.kind, 0) + 1
            probes.append(
                Probe(
                    name=f"{version.replace('.', '_')}_{record.kind}_{chosen[record.kind]}",
                    kind=record.kind,
                    version=version,
                    model=record.model,
                    field=record.field,
                    detail=record.detail,
                    successor=record.successor,
                )
            )
    covered = {probe.kind for probe in probes}
    return probes, sorted(set(CHANGE_CLASSES) - covered)


def _version_key(version: str) -> tuple:
    return tuple(int(part) if part.isdigit() else part for part in version.split("."))


def probe_state_sql(probes: list[Probe]) -> str:
    """What the migrated database says about each probe's subject.

    `ir_model` and `ir_model_fields` are ordinary tables: the answer needs no Odoo
    running, which matters because a step where the module failed to load is
    exactly the step worth asking about.
    """
    models = sorted({p.model for p in probes if p.subject_kind == "model"})
    fields = sorted({(p.model, p.field) for p in probes if p.subject_kind == "field"})
    # The successor too: a subject *and* its successor both absent means neither
    # was ever there, which is not the chain behaving.
    modules = sorted(
        {p.model for p in probes if p.subject_kind == "module"}
        | {p.successor for p in probes if p.subject_kind == "module" and p.successor}
    )
    parts: list[str] = []
    if models:
        parts.append(
            "SELECT 'model', model, '' FROM ir_model WHERE model IN ("
            + ", ".join(f"'{model}'" for model in models)
            + ")"
        )
    if modules:
        # `state` matters: a module row that survives as "uninstalled" is not a
        # module that is still there for anything that depended on it.
        parts.append(
            "SELECT 'module', name, '' FROM ir_module_module WHERE state != 'uninstalled' "
            "AND name IN (" + ", ".join(f"'{module}'" for module in modules) + ")"
        )
    if fields:
        parts.append(
            "SELECT 'field', model, name FROM ir_model_fields WHERE (model, name) IN ("
            + ", ".join(f"('{model}', '{field}')" for model, field in fields)
            + ")"
        )
    return " UNION ALL ".join(parts) + " ORDER BY 1, 2, 3"


@dataclass(frozen=True)
class ProbeVerdict:
    probe: Probe
    state: str

    @property
    def is_finding(self) -> bool:
        return self.state in ("gone unannounced", "still there")


#: Worst first: the two findings, then what behaved — and last, what could not
#: be observed at all, which is neither.
_VERDICT_ORDER = (
    "gone unannounced", "still there", "gone as predicted", "intact", "not observed"
)


def read_probe_states(
    probes: list[Probe], rows: list[list[str]], installed: bool = True
) -> list[ProbeVerdict]:
    """What became of each probe's subject, findings first.

    ``installed`` is False when the module's own table is not in the database: the
    module did not install, which is the answer, and reporting every probe as
    intact would be the wrong one.
    """
    if not installed:
        return [ProbeVerdict(probe, "absent") for probe in probes]
    present = {
        (row[0], row[1], row[2]) for row in rows if len(row) >= 3
    }
    verdicts: list[ProbeVerdict] = []
    for probe in probes:
        key = (probe.subject_kind, probe.model, probe.field if probe.field else "")
        there = key in present
        if there:
            state = "still there" if probe.expected_gone else "intact"
        elif not probe.expected_gone:
            state = "gone unannounced"
        elif probe.successor and (probe.subject_kind, probe.successor, "") not in present:
            # Neither the subject nor what it became is in the database, so this
            # probe measured nothing: the subject was never installed here.
            # Calling that "gone as predicted" reassures without having looked.
            state = "not observed"
        else:
            state = "gone as predicted"
        verdicts.append(ProbeVerdict(probe, state))
    verdicts.sort(
        key=lambda v: (_VERDICT_ORDER.index(v.state), _version_key(v.probe.version), v.probe.name)
    )
    return verdicts


#: The probes as the module itself recorded them, on the source version. Read
#: from the database rather than re-derived, so the check answers for the tester
#: that was actually installed and not for the one this version would choose.
#: Tabs are replaced because the rows come back tab-separated; an analysis line
#: holding one would split into a probe that does not exist.
def probe_rows_sql(successor: bool = True) -> str:
    """The probes as the module itself recorded them, on the source version.

    Read from the database rather than re-derived, so the check answers for the
    tester that was actually installed and not for the one this version would
    choose — which also means the *column set* is that tester's. A module
    generated before ``successor`` existed has no such column, and naming it
    would fail the whole query, so the caller asks first.

    Tabs are replaced because the rows come back tab-separated; an analysis line
    holding one would split into a probe that does not exist.
    """
    columns = [
        "name", "kind", "step", "subject_model", "coalesce(subject_field, '')",
        "replace(coalesce(source_line, ''), E'\\t', ' ')",
    ]
    if successor:
        columns.append("coalesce(successor, '')")
    return f"SELECT {', '.join(columns)} FROM {PROBE_TABLE} ORDER BY step, name"


#: The column whose presence decides which form of the query to ask for.
PROBE_SUCCESSOR_COLUMN = "successor"


def probes_from_rows(rows: list[list[str]]) -> list[Probe]:
    """The probe rows, read. A row that is short or names a class this version
    does not know is skipped: the module may have been generated by another."""
    probes: list[Probe] = []
    for row in rows:
        if len(row) < 6 or row[1] not in CHANGE_CLASSES:
            continue
        probes.append(
            Probe(
                name=row[0], kind=row[1], version=row[2], model=row[3],
                field=row[4], detail=row[5],
                # A module generated before this column existed has six columns.
                successor=row[6] if len(row) > 6 else "",
            )
        )
    return probes


def module_fate_changes(fates: list) -> list[ChangeRecord]:
    """Module fates, as change records a probe can be chosen from.

    The bridge between the two sources: analysis files state what happens to
    models and fields, ``apriori.py`` what happens to modules, and a probe is
    checked the same way whichever it came from. ``fates`` are
    ``preflight.ModuleFate``; a module nothing declares is not a change and is
    dropped here.
    """
    changes: list[ChangeRecord] = []
    for fate in fates:
        if fate.kind not in ("renamed", "merged"):
            continue
        kind = f"{fate.kind}_module"
        detail = (
            f"apriori.py: {fate.module} "
            + ("merged into " if fate.kind == "merged" else "renamed to ")
            + f"{fate.successor}"
        )
        changes.append(
            ChangeRecord(
                module=fate.module, model=fate.module, field="", kind=kind, detail=detail,
                successor=fate.successor,
            )
        )
    return changes
