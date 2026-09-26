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
                reason: str, today: str, before_chain: bool = False) -> dict:
    entry: dict = {"module": module, "source": source, "target": target, "decision": kind,
                   "reason": reason,
                   "evidence": {"checked": today, "recorded_by": "migrate decide"}}
    if to:
        entry["to"] = to[0] if kind == "renamed" and len(to) == 1 else list(to)
    if before_chain:
        entry["when"] = carry.BEFORE_CHAIN
    return entry


def build_loss(name: str, source: str, target: str, reason: str, today: str) -> dict:
    return {"name": name, "source": source, "target": target, "reason": reason,
            "evidence": {"checked": today, "recorded_by": "migrate accept-loss"}}


def merged_loss(text: str | None, loss: dict) -> str:
    """The file with ``loss`` in place of the same name's accepted loss for the pair, or
    appended. A bare-list file becomes the wrapper object, keeping its decisions."""
    data: object = {"decisions": []} if not (text or "").strip() else json.loads(text or "")
    if isinstance(data, list):
        data = {"decisions": data}
    if not isinstance(data, dict):
        raise ValueError(t("The decisions file holds no list of decisions."))
    losses = data.setdefault("accepted_losses", [])
    if not isinstance(losses, list):
        raise ValueError(t("The decisions file's accepted losses are not a list."))
    key = (loss["name"], loss["source"], loss["target"])
    for index, existing in enumerate(losses):
        if isinstance(existing, dict) and \
                (existing.get("name"), existing.get("source"), existing.get("target")) == key:
            losses[index] = loss
            break
    else:
        losses.append(loss)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


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
                    reason: str, write: bool, before_chain: bool = False) -> int:
    env = _environment(source, target)
    if env is None:
        return UNKNOWN
    if not carry.is_module_name(module):
        print(level_text("ERROR", tf("{} is not a module name.", module)))
        return FOUND
    entry = build_entry(module, env.source, env.target, kind, to, reason, date.today().isoformat(),
                        before_chain)
    problems = carry.entry_problems(entry)
    for level, code, args in problems:
        print(level_text("ERROR" if level == carry.BLOCKING else "WARN",
                         f"{module}: " + tf(carry.MESSAGES[code], *args)))
    if any(level == carry.BLOCKING for level, _, _ in problems):
        return FOUND
    print(json.dumps(entry, indent=2, ensure_ascii=False))
    return _write(env, lambda text: merged(text, entry), write)


def record_loss(name: str, source: str, target: str, reason: str, write: bool) -> int:
    """Accept, by name, a table or column that retiring modules before the chain may empty."""
    env = _environment(source, target)
    if env is None:
        return UNKNOWN
    loss = build_loss(name, env.source, env.target, reason, date.today().isoformat())
    result = carry.retirement([], [[name, reason]], env.source, env.target, set(), {})
    if result["problems"]:
        print(level_text("ERROR", tf(carry.MESSAGES["bad-loss"], name)))
        return FOUND
    if not reason.strip():
        print(level_text("ERROR", t("An accepted loss needs its reason (--reason).")))
        return FOUND
    print(json.dumps(loss, indent=2, ensure_ascii=False))
    return _write(env, lambda text: merged_loss(text, loss), write)


def _write(env, merge, write: bool) -> int:
    """Merge into the environment's decisions file, and write it only with ``write``."""
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
        content = merge(text)
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
