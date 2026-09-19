#!/usr/bin/env python3
"""Check the generated OdooLS configuration against the language server's latest release.

Developer tooling, not part of the package: ``odoo_dwg`` never imports this. Run it
when reviewing whether the official Odoo extension has moved, and before changing
what ``templates.render_odools_toml`` emits:

    python tools/verify_odools_config.py

What it does, in order (see docs/editor-integration.md for how to act on it):

1. Finds the latest **stable** release of ``odoo/odoo-ls`` (prereleases are
   reported, never used to judge: their keys are not yet safe to emit).
2. Downloads that release's ``config_schema.json`` — the schema OdooLS validates
   ``odools.toml`` against. It is strict (``additionalProperties: false``), so a key
   it does not know breaks the whole file.
3. Fails if any key the generator emits (``templates.ODOOLS_KEYS``) is missing from
   the schema or no longer accepts the type the generator writes.
4. Lists the schema keys the generator does not emit — candidate features to
   consider, never adopted automatically.
5. Prints the changelog entries newer than ``templates.ODOOLS_REVIEWED_VERSION``, so
   the reviewer reads what changed since the last review.

Exits 0 when every emitted key is still accepted, 1 when one is not or a source
cannot be read. It never edits the generator.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from odoo_dwg.templates import (  # noqa: E402
    ODOO_EXTENSION_ID,
    ODOOLS_KEYS,
    ODOOLS_REVIEWED_VERSION,
)

TIMEOUT = 30
SERVER_REPO = "odoo/odoo-ls"
EXTENSION_REPO = "odoo/odoo-vscode"
RELEASES_URL = "https://api.github.com/repos/{repo}/releases?per_page=30"
# Read from the newest release's *tag*, not a branch: prerelease notes live on the
# `beta` branch only, so master and release both look up to date when they are not.
# And read both files: upstream keeps only the latest entry in changelog.md and
# moves every earlier one to changelog_archive.md.
CHANGELOG_URL = "https://raw.githubusercontent.com/odoo/odoo-ls/{ref}/{name}"
CHANGELOG_FILES = ("changelog.md", "changelog_archive.md")
SCHEMA_ASSET = "config_schema.json"

# The JSON type each emitted key is written as. The schema may allow more (for
# instance ``null``); what matters is that it still allows ours.
EMITTED_TYPES = {
    "name": "string",
    "odoo_path": "string",
    "addons_paths": "array",
    "python_path": "string",
}


class SourceError(RuntimeError):
    """A source could not be read, so nothing can be concluded from it."""


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise SourceError(f"{url}: {error}") from error


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text)[:3])


def releases(repo: str) -> list[dict]:
    data = json.loads(fetch(RELEASES_URL.format(repo=repo)))
    return [r for r in data if not r.get("draft")]


def latest(releases_list: list[dict], prerelease: bool) -> dict | None:
    candidates = [r for r in releases_list if bool(r.get("prerelease")) is prerelease]
    return max(candidates, key=lambda r: version_tuple(r["tag_name"]), default=None)


def entry_properties(schema: dict) -> tuple[dict, object]:
    """The per-profile properties and the ``additionalProperties`` setting, wherever
    the schema keeps them (inline or behind a ``$ref``)."""
    config = schema.get("properties", {}).get("config", {})
    item = config.get("items", config)
    ref = item.get("$ref")
    if ref:
        name = ref.rsplit("/", 1)[-1]
        item = (schema.get("$defs") or schema.get("definitions") or {}).get(name, {})
    return item.get("properties", {}), item.get("additionalProperties")


def accepted_types(spec: dict) -> set[str]:
    kinds = spec.get("type")
    if isinstance(kinds, str):
        return {kinds}
    if isinstance(kinds, list):
        return set(kinds)
    found: set[str] = set()
    for option in spec.get("anyOf", []) + spec.get("oneOf", []):
        found |= accepted_types(option)
    return found


def changelog_since(reviewed: str, ref: str) -> list[tuple[str, str]]:
    """``(heading, body)`` for every changelog section newer than ``reviewed``, as
    recorded at ``ref`` (the newest release tag, so prerelease notes are included)."""
    found: dict[tuple[int, ...], tuple[str, str]] = {}
    for name in CHANGELOG_FILES:
        text = fetch(CHANGELOG_URL.format(ref=ref, name=name)).decode("utf-8", errors="replace")
        for section in re.split(r"(?m)^(?=## \[)", text):
            match = re.match(r"## \[([^\]]+)\]([^\n]*)\n(.*)", section, re.S)
            if not match or version_tuple(match.group(1)) <= version_tuple(reviewed):
                continue
            heading = f"[{match.group(1)}]{match.group(2)}".strip()
            # The same version in both files: the first one read (changelog.md) wins.
            found.setdefault(version_tuple(match.group(1)), (heading, match.group(3).strip()))
    return [found[key] for key in sorted(found, reverse=True)]


def main() -> int:
    problems: list[str] = []
    try:
        server = releases(SERVER_REPO)
    except SourceError as error:
        print(f"ERROR  cannot list {SERVER_REPO} releases: {error}")
        return 1
    stable = latest(server, prerelease=False)
    beta = latest(server, prerelease=True)
    if stable is None:
        print(f"ERROR  {SERVER_REPO} has no stable release to judge against")
        return 1

    print(f"OdooLS stable:     {stable['tag_name']}  ({stable.get('published_at', '')[:10]})")
    if beta and version_tuple(beta["tag_name"]) > version_tuple(stable["tag_name"]):
        print(f"OdooLS prerelease: {beta['tag_name']}  ({beta.get('published_at', '')[:10]})"
              "  — reported only; its keys are not judged")
    print(f"Reviewed against:  {ODOOLS_REVIEWED_VERSION}  (templates.ODOOLS_REVIEWED_VERSION)")
    try:
        extension = latest(releases(EXTENSION_REPO), prerelease=False)
        if extension:
            print(f"{ODOO_EXTENSION_ID} stable: {extension['tag_name']}")
    except SourceError as error:
        print(f"WARN   cannot list {EXTENSION_REPO} releases: {error}")

    asset = next((a for a in stable.get("assets", []) if a["name"] == SCHEMA_ASSET), None)
    if asset is None:
        print(f"ERROR  release {stable['tag_name']} publishes no {SCHEMA_ASSET}")
        return 1
    try:
        schema = json.loads(fetch(asset["browser_download_url"]))
    except (SourceError, json.JSONDecodeError) as error:
        print(f"ERROR  cannot read {SCHEMA_ASSET}: {error}")
        return 1
    properties, additional = entry_properties(schema)
    strict = additional is False
    print(f"\nSchema {stable['tag_name']}: {len(properties)} keys per profile, "
          f"{'strict (unknown keys rejected)' if strict else 'lenient'}")

    print("\nEmitted keys:")
    for key in ODOOLS_KEYS:
        spec = properties.get(key)
        if spec is None:
            problems.append(f"{key}: not accepted by the {stable['tag_name']} schema")
            print(f"  FAIL  {key}: not in the schema")
            continue
        wanted = EMITTED_TYPES.get(key)
        kinds = accepted_types(spec)
        if wanted and kinds and wanted not in kinds:
            problems.append(f"{key}: schema accepts {sorted(kinds)}, generator writes {wanted}")
            print(f"  FAIL  {key}: accepts {sorted(kinds)}, we write {wanted}")
        else:
            print(f"  ok    {key}  ({'/'.join(sorted(kinds)) or 'untyped'})")

    unused = sorted(set(properties) - set(ODOOLS_KEYS))
    print(f"\nKeys the generator does not emit ({len(unused)}) — candidates to review, not adopt:")
    for key in unused:
        description = (properties[key].get("description") or "").split("\n")[0][:90]
        print(f"  -  {key}" + (f": {description}" if description else ""))

    newest = max((beta, stable), key=lambda r: version_tuple(r["tag_name"]) if r else ())
    print(f"\nChangelog since {ODOOLS_REVIEWED_VERSION} (as of {newest['tag_name']}):")
    try:
        newer = changelog_since(ODOOLS_REVIEWED_VERSION, newest["tag_name"])
    except SourceError as error:
        problems.append(f"changelog unreadable: {error}")
        newer = []
    if not newer:
        print("  (nothing newer)")
    for heading, body in newer:
        channel = (
            "prerelease" if version_tuple(heading) > version_tuple(stable["tag_name"])
            else "stable"
        )
        print(f"\n  ## {heading}   <{channel}>")
        for line in body.splitlines()[:25]:
            print(f"     {line}")
        if len(body.splitlines()) > 25:
            print("     … (truncated — read the full entry in changelog.md)")

    print()
    if problems:
        print(f"{len(problems)} problem(s):")
        for line in problems:
            print(f"  - {line}")
        print("\nThe generator was NOT modified. See docs/editor-integration.md.")
        return 1
    print("Every emitted key is accepted by the latest stable schema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
