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
_EXPECTED_GONE = frozenset({"removed_field", "removed_model", "renamed_model"})


@dataclass(frozen=True)
class Probe:
    """One declared expectation about one upstream subject."""

    name: str
    kind: str
    version: str     # the step whose analysis declared it
    model: str
    field: str       # "" for a model-level subject
    detail: str      # the analysis line, verbatim

    @property
    def subject(self) -> str:
        return f"{self.model}/{self.field}" if self.field else self.model

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
    models = sorted({probe.model for probe in probes})
    fields = sorted({(probe.model, probe.field) for probe in probes if probe.field})
    parts = [
        "SELECT 'model', model, '' FROM ir_model WHERE model IN ("
        + ", ".join(f"'{model}'" for model in models)
        + ")"
    ]
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


#: Worst first: the two findings, then what behaved.
_VERDICT_ORDER = ("gone unannounced", "still there", "gone as predicted", "intact")


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
        key = ("field", probe.model, probe.field) if probe.field else ("model", probe.model, "")
        there = key in present
        if there:
            state = "still there" if probe.expected_gone else "intact"
        else:
            state = "gone as predicted" if probe.expected_gone else "gone unannounced"
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
PROBE_ROWS_SQL = (
    "SELECT name, kind, step, subject_model, coalesce(subject_field, ''), "
    "replace(coalesce(source_line, ''), E'\\t', ' ') "
    f"FROM {PROBE_TABLE} ORDER BY step, name"
)


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
            )
        )
    return probes
