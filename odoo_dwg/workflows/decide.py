"""Record a module decision from the command line.

The one non-interactive command that writes: it changes only the environment's own
operator record, ``decisions.json``, and only with ``--write``. Without it, it prints the
entry it would record. The entry for the same module and pair is replaced where it stands;
every other entry, and anything else in the file, is left as it was.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from .. import carry
from ..i18n import t, tf
from ..planners import write_text_file_command
from ..system import apply_commands, read_text
from ..ui import level_text
from .checks import CLEAN, FOUND, UNKNOWN, _environment


def build_entry(module: str, source: str, target: str, kind: str, to: list[str],
                reason: str, today: str) -> dict:
    entry: dict = {"module": module, "source": source, "target": target, "decision": kind,
                   "reason": reason,
                   "evidence": {"checked": today, "recorded_by": "migrate decide"}}
    if to:
        entry["to"] = to[0] if kind == "renamed" and len(to) == 1 else list(to)
    return entry


def merged(text: str | None, entry: dict) -> str:
    """The file with ``entry`` in place of the same module's entry for the pair, or appended.

    Keeps the file's shape (a wrapper object or a bare list) and its other keys. A file that
    cannot be read is refused rather than overwritten: it is the operator's record."""
    data: object = {"decisions": []} if not (text or "").strip() else json.loads(text or "")
    entries = data.get("decisions") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise ValueError(t("The decisions file holds no list of decisions."))
    key = (entry["module"], entry["source"], entry["target"])
    for index, existing in enumerate(entries):
        if isinstance(existing, dict) and \
                (existing.get("module"), existing.get("source"), existing.get("target")) == key:
            entries[index] = entry
            break
    else:
        entries.append(entry)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def record_decision(module: str, source: str, target: str, kind: str, to: list[str],
                    reason: str, write: bool) -> int:
    env = _environment(source, target)
    if env is None:
        return UNKNOWN
    if not carry.is_module_name(module):
        print(level_text("ERROR", tf("{} is not a module name.", module)))
        return FOUND
    entry = build_entry(module, env.source, env.target, kind, to, reason, date.today().isoformat())
    problems = carry.entry_problems(entry)
    for level, code, args in problems:
        print(level_text("ERROR" if level == carry.BLOCKING else "WARN",
                         f"{module}: " + tf(carry.MESSAGES[code], *args)))
    if any(level == carry.BLOCKING for level, _, _ in problems):
        return FOUND
    print(json.dumps(entry, indent=2, ensure_ascii=False))
    if not env.root.is_dir():
        print(level_text("ERROR", tf("No migration environment at {}.", str(env.root))))
        return UNKNOWN
    # Written where it really is: a decisions file linked from a shared one stays linked.
    path = Path(os.path.realpath(env.decisions_file))
    text = read_text(str(path))
    if text is None and path.exists():
        # Unreadable is not empty: writing would replace every decision in it.
        print(level_text("ERROR", tf("Cannot read {}: {}", str(path), t("permission denied"))))
        return UNKNOWN
    try:
        content = merged(text, entry)
    except ValueError as error:
        print(level_text("ERROR", tf("Cannot read {}: {}", str(path), error)))
        return UNKNOWN
    if not write:
        print(level_text("INFO", tf("Not written. Add --write to record it in {}.", str(path))))
        return CLEAN
    mode = f"{path.stat().st_mode & 0o777:o}" if path.exists() else "644"
    try:
        apply_commands(write_text_file_command(path, content, mode))
    except RuntimeError:
        return UNKNOWN
    return CLEAN
