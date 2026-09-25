"""The client-modules stage: what it does with the operator's decisions at the target.

After the chain, a client's own modules can be carried to new names: ``renamed`` to one
module (several renamed to the same one are merged into it), ``replaced`` by one or more
modules, or ``dropped``. This module turns the decisions into the stage's plan and names
what would stop it.

It is the one place that logic lives. ``migrate modules`` imports it; the migration driver
cannot import the tool, so it embeds this file's source verbatim and runs it with the host's
``python3``. Hence the rules for this file: standard library only, no imports from the
package, and nothing at module level but definitions.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys

#: What the decisions file may say about a module. The first three predate this stage and
#: only settle coverage; the stage acts on the last three.
KINDS = ("kept", "deferred", "dropped", "renamed", "replaced")
CARRY_KINDS = ("renamed", "replaced", "dropped")

#: An Odoo module's technical name. Every name the plan hands to a shell or to Odoo is one.
_MODULE_NAME = re.compile(r"^[a-z0-9_]+$")

BLOCKING = "blocking"
WARNING = "warning"

#: Each problem's text, by code. English, because the driver's output is a generated
#: artifact; ``migrate modules`` passes the same text through its translations.
MESSAGES = {
    "unknown-kind": "unknown decision {}: the stage ignores it",
    "no-to": "{} names no module in `to`",
    "many-to": "renamed to more than one module ({})",
    "to-on-kind": "`to` is only for renamed or replaced, not {}",
    "bad-name": "{} is not a module name",
    "to-itself": "carried to itself",
    "unresolved": "{} resolves in none of the {} sources",
    "no-manifest": "{} has no readable manifest",
    "wrong-series": "{} is version {}, not {}",
    "no-migrations": "{} has no migrations/ scripts",
    "not-installable": "{} is not installable (its manifest says installable: False)",
    "merge-installed":
        "{} is already installed: merging into it runs none of its migration scripts",
}


def is_module_name(name: str) -> bool:
    return bool(_MODULE_NAME.match(name))


def targets(entry: dict) -> list[str]:
    """The module(s) an entry's ``to`` names, as read: a string or a list of strings."""
    to = entry.get("to")
    if isinstance(to, str):
        return [to] if to else []
    if isinstance(to, list):
        return [str(item) for item in to]
    return []


def entry_problems(entry: dict) -> list[tuple[str, str, list]]:
    """What is wrong with one decision on its own, as ``(level, code, args)``."""
    kind = entry.get("decision", "")
    to = targets(entry)
    problems: list[tuple[str, str, list]] = []
    if kind not in KINDS:
        return [(WARNING, "unknown-kind", [kind])]
    if kind in ("renamed", "replaced") and not to:
        problems.append((BLOCKING, "no-to", [kind]))
    if kind == "renamed" and len(to) > 1:
        problems.append((BLOCKING, "many-to", [", ".join(to)]))
    if kind not in ("renamed", "replaced") and "to" in entry:
        problems.append((BLOCKING, "to-on-kind", [kind]))
    for name in to:
        if not is_module_name(name):
            problems.append((BLOCKING, "bad-name", [name]))
        elif name == entry.get("module"):
            problems.append((BLOCKING, "to-itself", []))
    return problems


def message(problem: dict) -> str:
    """A problem's English text."""
    return MESSAGES[problem["code"]].format(*problem["args"])


def _series_ok(version: str, target: str) -> bool:
    """A manifest version Odoo loads at ``target``: five parts starting with the series,
    or a short one Odoo prefixes with it."""
    parts = version.split(".")
    if len(parts) <= 3:
        return True
    return ".".join(parts[:2]) == target


def reader(sources: list[str]):
    """``read(name)`` over the target's sources, in addons-path order: ``None`` when the
    module resolves nowhere, else ``{"path", "manifest", "migrations"}`` with the manifest
    parsed (never executed), ``None`` when it cannot be read."""

    def read(name: str):
        for src in sources:
            path = os.path.join(src, name)
            if not os.path.isdir(path):
                continue
            manifest = None
            for filename in ("__manifest__.py", "__openerp__.py"):
                try:
                    with open(os.path.join(path, filename), encoding="utf-8") as handle:
                        data = ast.literal_eval(handle.read())
                except (OSError, ValueError, SyntaxError, TypeError):
                    continue
                if isinstance(data, dict):
                    manifest = data
                    break
            return {"path": path, "manifest": manifest,
                    "migrations": os.path.isdir(os.path.join(path, "migrations"))}
        return None

    return read


def plan(entries: list, source: str, target: str, read, installed=None) -> dict:
    """The stage's plan for one source -> target pair.

    ``installed`` is the set of modules installed in the database, or ``None`` when no
    database was read: then every decided module is planned as if installed.
    """
    renames: list[list[str]] = []
    installs: list[str] = []
    uninstalls: list[str] = []
    skipped: list[str] = []
    left: list[str] = []
    merges: list[str] = []
    problems: list[dict] = []

    def problem(module: str, level: str, code: str, args: list) -> None:
        problems.append({"module": module, "level": level, "code": code, "args": args})

    def check_target(module: str, name: str) -> bool:
        found = read(name)
        if found is None:
            problem(module, BLOCKING, "unresolved", [name, target])
            return False
        manifest = found["manifest"]
        if manifest is None:
            problem(module, BLOCKING, "no-manifest", [name])
            return False
        version = str(manifest.get("version", ""))
        if version and not _series_ok(version, target):
            problem(module, BLOCKING, "wrong-series", [name, version, target])
            return False
        if manifest.get("installable", True) is False:
            # Odoo would skip it and still exit 0, and the old module would then go.
            problem(module, BLOCKING, "not-installable", [name])
            return False
        return True

    pair = [e for e in entries if isinstance(e, dict)
            and e.get("source") == source and e.get("target") == target and e.get("module")]
    for entry in sorted(pair, key=lambda e: e["module"]):
        module = entry["module"]
        kind = entry.get("decision", "")
        own = entry_problems(entry)
        for level, code, args in own:
            problem(module, level, code, args)
        if any(level == BLOCKING for level, _, _ in own) or kind not in KINDS:
            continue
        present = installed is None or module in installed
        if kind in ("kept", "deferred"):
            if installed is not None and present and read(module) is None:
                left.append(module)
            continue
        if not present:
            skipped.append(module)
            continue
        to = targets(entry)
        # Every target checked, so each problem is named; a module with one is not planned.
        if not all([check_target(module, name) for name in to]):
            continue
        if kind == "renamed":
            renames.append([module, to[0]])
            if installed is not None and to[0] in installed:
                problem(module, WARNING, "merge-installed", [to[0]])
            found = read(to[0])
            if found is not None and not found["migrations"]:
                problem(module, WARNING, "no-migrations", [to[0]])
        elif kind == "replaced":
            installs.extend(name for name in to
                            if installed is None or name not in installed)
            uninstalls.append(module)
        else:
            uninstalls.append(module)

    news = [new for _, new in renames]
    for new in sorted(set(news)):
        # Folded into a module the database already has, or one of several renamed to it.
        if (installed is not None and new in installed) or news.count(new) > 1:
            merges.append(new)
    return {
        "source": source,
        "target": target,
        "renames": renames,
        "merges": merges,
        "updates": sorted(set(news)),
        "installs": sorted(set(installs) - set(news)),
        "uninstalls": sorted(set(uninstalls)),
        "skipped": skipped,
        "left": left,
        "problems": problems,
    }


def has_work(result: dict) -> bool:
    return bool(result["renames"] or result["installs"] or result["uninstalls"])


def blocked(result: dict) -> bool:
    return any(p["level"] == BLOCKING for p in result["problems"])


def describe(result: dict) -> list[str]:
    """The plan in plain lines, the same wherever it is printed (in English: the driver's
    output is a generated artifact)."""
    lines = []
    for old, new in result["renames"]:
        how = "merged into" if new in result["merges"] else "renamed to"
        lines.append(f"{old} {how} {new}")
    for key in ("updates", "installs", "uninstalls"):
        if result[key]:
            lines.append(f"{key[:-1]}: {', '.join(result[key])}")
    target = result["target"]
    lines += [f"{module}: not installed, nothing to carry" for module in result["skipped"]]
    lines += [f"{module}: still installed with no code at {target} (kept as decided)"
              for module in result["left"]]
    lines += [f"{p['module']}: {message(p)} ({p['level']})" for p in result["problems"]]
    return lines


def read_decisions(path: str) -> list:
    """The decisions file's entries, in either shape the tool writes or a hand writes; an
    unreadable file decides nothing."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, TypeError):
        return []
    entries = data.get("decisions") if isinstance(data, dict) else data
    return entries if isinstance(entries, list) else []


def main(argv: list[str]) -> int:
    """The driver's entry: ``decisions source target plan_out sources...``.

    Installed modules come from ``ODWG_INSTALLED`` (one per line); unset, none were read.
    Writes the plan as JSON to ``plan_out``, its lines to stderr, and to stdout the
    modules to update and to install (comma-separated, one line each). Exits 1 when
    something blocks the stage, 3 when there is nothing to carry, 0 otherwise.
    """
    decisions, source, target, plan_out, *sources = argv
    raw = os.environ.get("ODWG_INSTALLED")
    installed = None if raw is None else {line.strip() for line in raw.splitlines()
                                          if line.strip()}
    result = plan(read_decisions(decisions), source, target, reader(sources), installed)
    with open(plan_out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    for line in describe(result):
        print(f"[modules] {line}", file=sys.stderr)
    if blocked(result):
        return 1
    if not has_work(result):
        return 3
    print(",".join(result["updates"]))
    print(",".join(result["installs"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
