#!/usr/bin/env python3
"""Re-derive the neutralisation catalogue's sources from the local clones.

Two questions, both about drift:

1. Which of Odoo's own ``data/neutralize.sql`` files (16.0-19.0) does the
   catalogue cover, and which not yet? A new file in a new release is a path to
   the outside nobody has looked at; this names it.
2. Does every file a rule cites still name the columns the rule writes? A rule
   citing a file that no longer mentions its column is remembering, not citing.

    python tools/verify_neutralise_sources.py

Reads ``~/odoo-migrations/.repos`` (``odoo-<v>``, ``openupgrade-13.0`` for 13.0,
and ``oca-trees/<repo>-<v>`` for OCA citations, fetched lazily by git when a
blob is not local). Exits non-zero when a cited file lacks a column it should
name; files not covered are reported, not failed — covering them is a decision.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odoo_dwg import neutralise  # noqa: E402

REPOS = Path.home() / "odoo-migrations" / ".repos"
OFFICIAL = ("16.0", "17.0", "18.0", "19.0")
_ODOO_CITE = re.compile(r"odoo (\d+\.0)(?:-(\d+\.0))? ([\w/.]+)")
_OCA_CITE = re.compile(r"OCA/([\w-]+)")


def _odoo_tree(version: str) -> Path:
    return REPOS / ("openupgrade-13.0" if version == "13.0" else f"odoo-{version}")


def _versions(first: str, last: str | None) -> list[str]:
    lo, hi = int(float(first)), int(float(last or first))
    return [f"{major}.0" for major in range(lo, hi + 1)]


def _read(version: str, path: str) -> str | None:
    file = _odoo_tree(version) / path
    return file.read_text(errors="ignore") if file.is_file() else None


def _oca(repo: str, branch: str, path: str) -> str | None:
    tree = REPOS / "oca-trees" / f"{repo}-{branch}"
    if not tree.is_dir():
        return None
    shown = subprocess.run(["git", "-C", str(tree), "show", f"HEAD:{path}"],
                           capture_output=True, text=True)
    return shown.stdout if shown.returncode == 0 else None


def main() -> int:
    problems: list[str] = []
    print("== Odoo's own neutralize.sql files, and what covers them")
    official: dict[str, list[str]] = {}
    for version in OFFICIAL:
        tree = _odoo_tree(version)
        if not tree.is_dir():
            print(f"   {version}: no local clone at {tree}")
            continue
        for file in sorted(tree.glob("**/data/neutralize.sql")):
            official.setdefault(str(file.relative_to(tree).parent.parent), []).append(version)
    for module, versions in sorted(official.items()):
        citing = [r.id for r in neutralise.CATALOGUE if f"{module}/data/neutralize.sql" in r.source]
        print(f"   {module:<45} {versions[0]}-{versions[-1]:<5} "
              f"{', '.join(citing) if citing else 'not covered'}")

    print("\n== Every cited file still names the columns its rule writes")
    for rule in neutralise.CATALOGUE:
        columns = [c for c, _ in rule.sets]
        if rule.source.startswith("odoo_dwg"):
            print(f"   {rule.id:<30} own rule, no external source")
            continue
        for match in _ODOO_CITE.finditer(rule.source):
            first, last, path = match.group(1), match.group(2), match.group(3).split(":")[0]
            texts = {v: _read(v, path) for v in _versions(first, last)}
            found = {v: t for v, t in texts.items() if t is not None}
            if not found:
                print(f"   {rule.id:<30} {path}: no local copy for {first}-{last or first}")
                continue
            missing = [c for c in columns if not any(c in t for t in found.values())]
            state = f"MISSING {missing}" if missing else "ok"
            print(f"   {rule.id:<30} {path} ({', '.join(found)}): {state}")
            if missing:
                problems.append(f"{rule.id}: {path} does not name {missing}")
        oca = _OCA_CITE.search(rule.source)
        if oca:
            repo = oca.group(1)
            for segment in rule.source[oca.end():].split(";"):
                branches = re.findall(r"\d+\.0", segment)
                paths = re.findall(r"[\w/]+\.py", segment)
                for branch in branches:
                    for path in paths:
                        text = _oca(repo, branch, path)
                        if text is None:
                            print(f"   {rule.id:<30} OCA/{repo} {branch} {path}: no local tree")
                            continue
                        missing = [c for c in columns if c not in text]
                        print(f"   {rule.id:<30} OCA/{repo} {branch} {path}: "
                              f"{'MISSING ' + str(missing) if missing else 'ok'}")
                        if missing:
                            problems.append(f"{rule.id}: OCA/{repo} {branch} {path} does not "
                                            f"name {missing}")
    if problems:
        print("\n".join(["", "FAILED:", *problems]))
        return 1
    print("\nEvery cited source still names what its rule writes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
