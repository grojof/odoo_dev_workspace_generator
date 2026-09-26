"""The client-modules stage: what it does with the operator's decisions at the target.

After the chain, a client's own modules can be carried to new names: ``renamed`` to one
module (several renamed to the same one are merged into it; one renamed to several is split:
the first takes it, the others are installed), ``replaced`` by one or more
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
    "bad-when": "`when` can only be before-chain, on a dropped decision, not {}",
    "dependent": "{} depends on it and is installed, but is not retired before the chain",
    "bad-loss": "{} is not a table or table.column name",
}

#: When a ``dropped`` decision may act instead of at the target.
BEFORE_CHAIN = "before-chain"

#: A table or ``table.column`` of the source database, as an accepted loss names it.
_LOSS_NAME = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?$")


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
    if kind not in ("renamed", "replaced") and "to" in entry:
        problems.append((BLOCKING, "to-on-kind", [kind]))
    for name in to:
        if not is_module_name(name):
            problems.append((BLOCKING, "bad-name", [name]))
        elif name == entry.get("module"):
            problems.append((BLOCKING, "to-itself", []))
    if "when" in entry and (kind != "dropped" or entry.get("when") != BEFORE_CHAIN):
        problems.append((BLOCKING, "bad-when", [f"{entry.get('when')} on {kind}"]))
    return problems


def retires_before_chain(entry: dict) -> bool:
    return entry.get("decision") == "dropped" and entry.get("when") == BEFORE_CHAIN


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
    splits: dict[str, list[str]] = {}
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
            # Several modules: a split. The first takes the old module and its data; the
            # others are new parts, installed in the same run.
            renames.append([module, to[0]])
            if len(to) > 1:
                splits[module] = to[1:]
            installs.extend(name for name in to[1:]
                            if installed is None or name not in installed)
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
        "splits": splits,
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
        if old in result.get("splits", {}):
            lines.append(f"{old} split: its other parts {', '.join(result['splits'][old])} "
                         "are installed")
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


def read_accepted_losses(path: str, source: str, target: str) -> list:
    """The decisions file's accepted losses for the pair: ``[name, reason]``, where name is
    a table or ``table.column``. A file of the bare-list shape accepts none."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, TypeError):
        return []
    losses = data.get("accepted_losses") if isinstance(data, dict) else None
    return [[str(loss.get("name", "")), str(loss.get("reason", ""))]
            for loss in (losses if isinstance(losses, list) else [])
            if isinstance(loss, dict) and loss.get("source") == source
            and loss.get("target") == target]


def retirement(entries: list, losses: list, source: str, target: str, installed: set,
               depends: dict) -> dict:
    """What the driver retires right after the source restore, for one pair.

    ``installed`` is the set of installed modules; ``depends`` maps each installed module to
    the modules it depends on. A retired module takes along every installed module that
    depends on it, as Odoo's uninstall does: each of those must be retired as well.
    """
    problems: list[dict] = []

    def problem(module: str, code: str, args: list) -> None:
        problems.append({"module": module, "level": BLOCKING, "code": code, "args": args})

    pair = [e for e in entries if isinstance(e, dict)
            and e.get("source") == source and e.get("target") == target and e.get("module")]
    retire = []
    for entry in pair:
        own = entry_problems(entry)
        if any(level == BLOCKING for level, _, _ in own):
            continue
        if retires_before_chain(entry) and entry["module"] in installed:
            retire.append(entry["module"])
    retire = sorted(set(retire))
    # Every installed module that reaches a retired one through its dependencies.
    users: dict[str, set] = {}
    for module, deps in depends.items():
        for dep in deps:
            users.setdefault(dep, set()).add(module)
    for module in retire:
        seen, todo = set(), [module]
        while todo:
            for user in users.get(todo.pop(), ()):
                if user not in seen and user in installed:
                    seen.add(user)
                    todo.append(user)
        for user in sorted(seen - set(retire)):
            problem(module, "dependent", [user])
    accepted = []
    for name, reason in losses:
        if not _LOSS_NAME.match(name):
            problem(name, "bad-loss", [name])
        else:
            accepted.append([name, reason])
    return {"source": source, "target": target, "retire": retire, "accepted": accepted,
            "problems": problems}


def main_retire(argv: list[str]) -> int:
    """The driver's entry for the retirement: ``retire decisions source target plan_out``.

    Installed modules come from ``ODWG_INSTALLED`` (one per line) and dependencies from
    ``ODWG_DEPENDS`` (``module<TAB>dependency`` per line). Writes the plan as JSON to
    ``plan_out`` and its lines to stderr; prints the modules to retire, comma-separated.
    Exits 1 when something blocks it, 3 when there is nothing to retire, 0 otherwise.
    """
    decisions, source, target, plan_out = argv
    installed = {line.strip() for line in os.environ.get("ODWG_INSTALLED", "").splitlines()
                 if line.strip()}
    depends: dict[str, set] = {}
    for line in os.environ.get("ODWG_DEPENDS", "").splitlines():
        module, _, dep = line.partition("\t")
        if module.strip() and dep.strip():
            depends.setdefault(module.strip(), set()).add(dep.strip())
    result = retirement(read_decisions(decisions), read_accepted_losses(decisions, source, target),
                        source, target, installed, depends)
    with open(plan_out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    if result["retire"]:
        print(f"[retire] before the chain: {', '.join(result['retire'])}", file=sys.stderr)
    for name, reason in result["accepted"]:
        print(f"[retire] accepted loss: {name} ({reason})", file=sys.stderr)
    for p in result["problems"]:
        print(f"[retire] {p['module']}: {message(p)} ({p['level']})", file=sys.stderr)
    if blocked(result):
        return 1
    if not result["retire"]:
        return 3
    print(",".join(result["retire"]))
    return 0


def main(argv: list[str]) -> int:
    """The driver's entry: ``decisions source target plan_out sources...``, or
    ``retire decisions source target plan_out`` for the retirement before the chain.

    Installed modules come from ``ODWG_INSTALLED`` (one per line); unset, none were read.
    Writes the plan as JSON to ``plan_out``, its lines to stderr, and to stdout the
    modules to update and to install (comma-separated, one line each). Exits 1 when
    something blocks the stage, 3 when there is nothing to carry, 0 otherwise.
    """
    if argv and argv[0] == "retire":
        return main_retire(argv[1:])
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
