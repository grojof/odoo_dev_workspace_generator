"""What a migration run left behind, read back.

Three sources, none of them written by this module:

- the driver's own step log (``logs/steps.tsv``), one appended line per event;
- each step's Odoo log, whose line shape is Odoo's and is stated once in its
  ``odoo/netsvc.py`` — ``asctime pid LEVEL dbname logger: message`` — identical
  from 13.0 to 19.0 in the checkouts this tool clones;
- the outbound firewall's decisions from the system journal, which OpenSnitch
  writes as rfc5424 structured data (``ARG1`` the decision, ``ARG2`` the rule).

Pure: reading the files and asking the journal live in ``system`` and the
workflow. Nothing here classifies a warning by meaning — what an OpenUpgrade
step warns about is not something this project asserts without evidence, and the
first real migration is what produces it. Level, logger and count are facts the
line itself carries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

#: One appended line of the driver's step log: when, run, step, event, detail.
STEP_COLUMNS = 5


@dataclass(frozen=True)
class Event:
    when: str
    run: str
    step: str
    event: str
    detail: str = ""


def parse_steps(text: str) -> list[Event]:
    """Events from the driver's step log. A line that cannot be read is skipped:
    the file is appended to by a shell script that may be killed mid-write."""
    events: list[Event] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        fields = raw.split("\t")
        if len(fields) < STEP_COLUMNS - 1:
            continue
        fields += [""] * (STEP_COLUMNS - len(fields))
        events.append(Event(*fields[:STEP_COLUMNS]))
    return events


@dataclass
class StepRun:
    """One step of one run: when it ran, how it ended, and its window."""

    version: str
    started: str = ""
    ended: str = ""
    outcome: str = "unfinished"
    code: str = ""

    @property
    def window(self) -> tuple[str, str]:
        """What to ask the journal for. An unfinished step has no end, and the
        caller asks from its start to now rather than inventing one."""
        return (self.started, self.ended)


@dataclass
class Run:
    """One invocation of the driver, as its own events describe it."""

    run: str
    chain: str = ""
    started: str = ""
    outcome: str = "unfinished"
    steps: list[StepRun] = field(default_factory=list)
    restored: list[str] = field(default_factory=list)

    def step(self, version: str) -> StepRun | None:
        return next((step for step in self.steps if step.version == version), None)


def runs(events: list[Event]) -> list[Run]:
    """Group events into runs, oldest first.

    A run is opened by its ``run-start``. Events carrying a run id that has not
    been opened still get one, so a file whose first lines were lost — or one
    written by a driver older than the step log — is read rather than dropped.
    """
    ordered: list[Run] = []
    by_id: dict[str, Run] = {}

    def ensure(event: Event) -> Run:
        run = by_id.get(event.run)
        if run is None:
            run = Run(run=event.run, started=event.when)
            by_id[event.run] = run
            ordered.append(run)
        return run

    for event in events:
        run = ensure(event)
        if event.event == "run-start":
            run.chain, run.started = event.detail, event.when
            continue
        if event.event == "run-ok":
            run.outcome = "ok"
            continue
        if event.event == "restore":
            run.restored.append(event.detail)
            continue
        if event.step == "-":
            continue
        step = run.step(event.step)
        if step is None:
            step = StepRun(version=event.step)
            run.steps.append(step)
        if event.event == "start":
            step.started, step.outcome = event.when, "unfinished"
        elif event.event == "ok":
            step.ended, step.outcome = event.when, "ok"
        elif event.event == "fail":
            step.ended, step.outcome, step.code = event.when, "fail", event.detail
            run.outcome = "fail"
        elif event.event == "skip":
            step.started = step.started or event.when
            step.ended, step.outcome = event.when, "skip"
    return ordered


def _elapsed(start: str, end: str) -> str:
    """How long a step took, or has been taking. "" when it cannot be told —
    an unparseable timestamp is not worth a guess."""
    try:
        began = datetime.fromisoformat(start)
        finished = datetime.fromisoformat(end)
    except (TypeError, ValueError):
        return ""
    seconds = int((finished - began).total_seconds())
    if seconds < 0:
        return ""
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


@dataclass(frozen=True)
class LiveStep:
    version: str
    state: str
    elapsed: str = ""


def live_view(run: Run | None, chain: list[str], now: str) -> list[LiveStep]:
    """One row per step of the chain, as the run's own events describe it.

    ``now`` is injected rather than read here: a view that asks the clock itself
    cannot be tested against a fixed instant. A step the run has not reached is
    *pending* — shown, because what has not happened yet is part of knowing where
    a chain is.
    """
    rows: list[LiveStep] = []
    for version in chain:
        step = run.step(version) if run else None
        if step is None:
            rows.append(LiveStep(version=version, state="pending"))
            continue
        if step.outcome == "unfinished":
            rows.append(
                LiveStep(version=version, state="running", elapsed=_elapsed(step.started, now))
            )
            continue
        rows.append(
            LiveStep(
                version=version,
                state=step.outcome,
                elapsed=_elapsed(step.started, step.ended),
            )
        )
    return rows


def current_step(rows: list[LiveStep]) -> str:
    """The step a watcher should be reading the log of, or ""."""
    return next((row.version for row in rows if row.state == "running"), "")


# Odoo's own log line, stated once in `odoo/netsvc.py` and unchanged from 13.0 to
# 19.0: `%(asctime)s %(pid)s %(levelname)s %(dbname)s %(name)s: %(message)s`.
_ODOO_LINE = re.compile(
    r"^(?P<when>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+) +\d+ +"
    r"(?P<level>[A-Z]+) +\S+ +(?P<logger>[\w.]+): (?P<message>.*)$"
)
#: Levels worth a report. `INFO` is the running commentary of a migration.
NOTEWORTHY_LEVELS = ("CRITICAL", "ERROR", "WARNING")


@dataclass(frozen=True)
class LogEntry:
    level: str
    logger: str
    count: int
    first: str


def summarise_log(text: str, levels: tuple[str, ...] = NOTEWORTHY_LEVELS) -> list[LogEntry]:
    """A step's log, deduplicated by (level, logger, message), worst level first.

    Deduplicated because one broken field can emit the same warning per record,
    and a report that repeats it ten thousand times hides the other nine.
    """
    seen: dict[tuple[str, str, str], int] = {}
    for line in text.splitlines():
        match = _ODOO_LINE.match(line)
        if not match or match["level"] not in levels:
            continue
        key = (match["level"], match["logger"], match["message"].strip())
        seen[key] = seen.get(key, 0) + 1
    order = {level: index for index, level in enumerate(levels)}
    entries = [
        LogEntry(level=level, logger=logger, count=count, first=message)
        for (level, logger, message), count in seen.items()
    ]
    entries.sort(key=lambda entry: (order.get(entry.level, 99), -entry.count, entry.logger))
    return entries


# OpenSnitch writes rfc5424 structured data: `[SRC="…" DSTHOST="…" ARG1="allow"
# ARG2="<rule>" …]`. `ARG1` is the decision and `ARG2` the rule that made it.
_JOURNAL_FIELD = re.compile(r'(\w+)="([^"]*)"')


@dataclass(frozen=True)
class Decision:
    action: str
    rule: str
    host: str
    process: str
    count: int = 1


def summarise_decisions(text: str, process: str = "") -> list[Decision]:
    """Firewall decisions from journal lines, deduplicated and counted.

    ``process`` keeps only the lines whose command or path mentions it — the
    step's own `odoo-bin`, so a report says what *the migration* reached for
    rather than everything the host did while it ran.
    """
    seen: dict[tuple[str, str, str, str], int] = {}
    for line in text.splitlines():
        fields = dict(_JOURNAL_FIELD.findall(line))
        if not fields.get("ARG1"):
            continue
        command = f"{fields.get('CMDLINE', '')} {fields.get('PATH', '')}"
        if process and process not in command:
            continue
        key = (
            fields["ARG1"],
            fields.get("ARG2", ""),
            fields.get("DSTHOST") or fields.get("DST", ""),
            command.strip(),
        )
        seen[key] = seen.get(key, 0) + 1
    decisions = [
        Decision(action=action, rule=rule, host=host, process=command, count=count)
        for (action, rule, host, command), count in seen.items()
    ]
    # Refusals first: on a host with the outbound firewall, `odoo-bin` is
    # rejected anywhere but localhost, so a rejection is the interesting half.
    decisions.sort(key=lambda d: (d.action == "allow", -d.count, d.host))
    return decisions
