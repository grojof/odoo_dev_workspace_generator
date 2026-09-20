#!/usr/bin/env python3
"""Re-derive the support matrix from its official sources and report any drift.

Developer tooling, not part of the package: ``odoo_dwg`` never imports this, and
like the other tools/verify_*.py checks, it reaches the network. Run it when an
Odoo branch may have changed what it targets, or before trusting a bound:

    python tools/verify_support_matrix.py            # every version
    python tools/verify_support_matrix.py 18.0 19.0  # only these

Exits 0 when every declared bound agrees with its source, 1 on drift or on a
source that could not be read. It never edits the declared matrix.

Sources, in precedence order per fact (see docs/support-matrix.md):

* Python minimum  — every source that states it (``odoo/release.py``
  ``MIN_PY_VERSION`` where the branch has it, ``setup.py`` ``python_requires``,
  and the documentation page) is read, and the declared value must match one of
  them; a disagreement between sources is reported as such, not as drift, because
  Odoo 14 genuinely has one. Reading the documentation alone is not enough: it
  states minima only, its URL layout changes per era, and the 13.0 page carries
  no requirements text at all.
* Python maximum  — ``odoo/release.py`` ``MAX_PY_VERSION`` where declared (19.0
  only); otherwise derived from the newest ``python_version`` bucket in
  ``requirements.txt`` and the distribution its comment names. That derivation
  reproduces 19.0's declared maximum exactly, which is what makes it usable for
  the branches that declare none.
* PostgreSQL minimum — the version's source-install page ("supported versions:
  N.0 or above").
* Host facts — ``packages.ubuntu.com/<codename>/{python3,postgresql}``.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from odoo_dwg.models import (  # noqa: E402
    ODOO_RELEASE_PY_URL,
    ODOO_REQUIREMENTS_URL,
    ODOO_SETUP_PY_URL,
    ODOO_SUPPORT,
    SUPPORTED_HOSTS,
    odoo_docs_url,
    python_tuple,
)

TIMEOUT = 30
UBUNTU_PACKAGE_URL = "https://packages.ubuntu.com/{codename}/{package}"

# The Python each distribution a requirements comment can name ships as its
# system interpreter. The Ubuntu rows are re-checked against packages.ubuntu.com
# below; the Debian ones are stated here because Odoo's comments use them and
# packages.debian.org is not consulted by this script.
DISTRO_PYTHON = {
    "focal": "3.8",      # Ubuntu 20.04
    "bullseye": "3.9",   # Debian 11
    "jammy": "3.10",     # Ubuntu 22.04
    "bookworm": "3.11",  # Debian 12
    "noble": "3.12",     # Ubuntu 24.04
    "trixie": "3.13",    # Debian 13
    "resolute": "3.14",  # Ubuntu 26.04
}


class SourceError(RuntimeError):
    """A source could not be read, so nothing can be concluded from it."""


def fetch(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:  # noqa: S310
            return response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise SourceError(f"{url}: {error}") from error


def page_text(url: str) -> str:
    """HTML with tags stripped. The documentation pages are fetched directly and
    stripped locally: a summarising fetcher returns empty content for the older
    ones while reporting success."""
    html = fetch(url)
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


# --- derivations -----------------------------------------------------------


def derive_python_min(version: str) -> dict[str, str]:
    """Every reading of a branch's Python floor, keyed by source.

    More than one source states it and they do not always agree — Odoo 14's
    documentation says 3.7 while its ``setup.py`` declares ``>=3.6`` — so all
    readings are returned and the caller accepts a declared value that matches
    any of them, flagging the disagreement instead of calling it drift.
    """
    readings: dict[str, str] = {}
    release = _release_bound(version, "MIN_PY_VERSION")
    if release:
        readings[f"odoo/release.py@{version} MIN_PY_VERSION"] = release
    try:
        setup = fetch(ODOO_SETUP_PY_URL.format(version=version))
        match = re.search(r"python_requires\s*=\s*['\"]>=\s*([0-9.]+)['\"]", setup)
        if match:
            readings[f"setup.py@{version} python_requires"] = match.group(1)
    except SourceError:
        pass
    try:
        url = odoo_docs_url(version)
        match = re.search(r"requires Python (\d+\.\d+)", page_text(url))
        if match:
            readings[url] = match.group(1)
    except SourceError:
        pass
    if not readings:
        raise SourceError(f"Odoo {version}: no source states a Python minimum")
    return readings


def derive_python_max(version: str) -> tuple[str | None, str]:
    """``(value, source)`` for a branch's Python ceiling: the declared maximum
    where the branch has one, else the newest interpreter bucket's distribution.
    ``None`` when that bucket names no distribution."""
    release = _release_bound(version, "MAX_PY_VERSION")
    if release:
        return release, f"odoo/release.py@{version} MAX_PY_VERSION"

    requirements = fetch(ODOO_REQUIREMENTS_URL.format(version=version))
    newest = _newest_bucket(requirements)
    if newest is None:
        return None, f"requirements.txt@{version}: no python_version buckets"
    literal, distros = newest
    if not distros:
        return None, (
            f"requirements.txt@{version}: newest bucket (python_version {literal}) "
            "names no distribution"
        )
    # Several lines share the newest bucket; the newest distribution among them
    # is the one the branch is maintained for.
    ceiling = max(
        (DISTRO_PYTHON[name] for name in distros if name in DISTRO_PYTHON),
        key=python_tuple,
        default=None,
    )
    if ceiling is None:
        raise SourceError(f"requirements.txt@{version}: unknown distributions {sorted(distros)}")
    named = "/".join(sorted(distros))
    return ceiling, f"requirements.txt@{version} newest bucket targets {named}"


def _release_bound(version: str, name: str) -> str | None:
    """A ``(major, minor)`` tuple declared in ``odoo/release.py``, or None when
    that branch does not declare it (only 19.0 does today)."""
    try:
        release = fetch(ODOO_RELEASE_PY_URL.format(version=version))
    except SourceError:
        return None
    match = re.search(rf"{name}\s*=\s*\((\d+)\s*,\s*(\d+)\)", release)
    return f"{match.group(1)}.{match.group(2)}" if match else None


def _newest_bucket(requirements: str) -> tuple[str, set[str]] | None:
    """The highest ``python_version`` literal in the file, plus the distribution
    names commented on the lines that open a bucket at it."""
    literals = re.findall(r"python_version\s*[<>=!]+\s*'([0-9.]+)'", requirements)
    if not literals:
        return None
    newest = max(literals, key=python_tuple)
    distros: set[str] = set()
    for line in requirements.splitlines():
        if f"'{newest}'" not in line:
            continue
        # Only an open-ended upper bucket (>= / >) tells us what the branch
        # targets; a `< '3.12'` bucket is the *older* side of a split.
        if not re.search(rf"python_version\s*>=?\s*'{re.escape(newest)}'", line):
            continue
        for name in re.findall(r"#.*?\(([A-Za-z]+)\)", line):
            distros.add(name.lower())
    return newest, distros


def derive_postgres_min(version: str) -> tuple[str | None, str]:
    """``(value, source)`` for a version's PostgreSQL floor, from its docs page."""
    url = odoo_docs_url(version)
    text = page_text(url)
    match = re.search(r"supported versions?:\s*(\d+\.\d+)", text, re.IGNORECASE)
    if match:
        return match.group(1), url
    if "PostgreSQL" not in text:
        raise SourceError(f"{url}: no PostgreSQL text (the 13.0 page is a stub)")
    return None, f"{url}: states no floor"


def derive_host_facts(codename: str) -> tuple[str, str]:
    """``(python3 minor, postgresql major)`` for an Ubuntu release."""
    python_text = page_text(UBUNTU_PACKAGE_URL.format(codename=codename, package="python3"))
    python_match = re.search(r"Package: python3 \((\d+\.\d+)", python_text)
    postgres_text = page_text(UBUNTU_PACKAGE_URL.format(codename=codename, package="postgresql"))
    postgres_match = re.search(r"Package: postgresql \((\d+)", postgres_text)
    if not python_match or not postgres_match:
        raise SourceError(f"packages.ubuntu.com/{codename}: could not read package versions")
    return python_match.group(1), postgres_match.group(1)


# --- comparison ------------------------------------------------------------


class Report:
    def __init__(self) -> None:
        self.drift: list[str] = []
        self.errors: list[str] = []
        self.notes: list[str] = []
        self.checked = 0

    def compare(self, what: str, declared: str | None, derived: str | None, source: str) -> None:
        self.checked += 1
        if declared == derived:
            print(f"  ok      {what}: {declared or 'not stated'}")
            return
        self.drift.append(
            f"{what}: declared {declared or 'not stated'}, "
            f"source says {derived or 'not stated'} ({source})"
        )
        print(f"  DRIFT   {what}: declared {declared or 'not stated'} != {derived or 'not stated'}")
        print(f"          source: {source}")

    def compare_any(self, what: str, declared: str | None, readings: dict[str, str]) -> None:
        """Accept ``declared`` when any source states it; note a disagreement
        between sources without calling it drift."""
        self.checked += 1
        values = set(readings.values())
        if declared in values:
            note = ""
            if len(values) > 1:
                others = ", ".join(
                    f"{value} ({source})"
                    for source, value in sorted(readings.items())
                    if value != declared
                )
                note = f"  [sources disagree: also {others}]"
                self.notes.append(f"{what}: declared {declared}; {others}")
            print(f"  ok      {what}: {declared}{note}")
            return
        stated = ", ".join(f"{value} ({source})" for source, value in sorted(readings.items()))
        self.drift.append(f"{what}: declared {declared or 'not stated'}, sources state {stated}")
        print(f"  DRIFT   {what}: declared {declared or 'not stated'} stated by no source")
        print(f"          sources: {stated}")

    def failed(self, what: str, error: Exception) -> None:
        self.errors.append(f"{what}: {error}")
        print(f"  ERROR   {what}: {error}")


def verify_version(version: str, report: Report) -> None:
    support = ODOO_SUPPORT[int(version.split(".")[0])]
    print(f"Odoo {version}")
    try:
        report.compare_any(
            f"Odoo {version} python minimum",
            support.python_min.value,
            derive_python_min(version),
        )
    except SourceError as error:
        report.failed(f"Odoo {version} python minimum", error)

    for label, declared, derive in (
        ("python maximum", support.python_max.value, derive_python_max),
        ("postgresql minimum", support.postgres_min.value, derive_postgres_min),
    ):
        try:
            derived, source = derive(version)
        except SourceError as error:
            report.failed(f"Odoo {version} {label}", error)
            continue
        report.compare(f"Odoo {version} {label}", declared, derived, source)


def verify_hosts(report: Report) -> None:
    print("Hosts")
    for host in SUPPORTED_HOSTS:
        try:
            python, postgres = derive_host_facts(host.codename)
        except SourceError as error:
            report.failed(f"{host.name}", error)
            continue
        report.compare(f"{host.name} system python", host.system_python, python, host.codename)
        report.compare(f"{host.name} postgresql", host.postgres_major, postgres, host.codename)


def main(argv: list[str]) -> int:
    requested = argv[1:]
    versions = [ODOO_SUPPORT[major].version for major in sorted(ODOO_SUPPORT)]
    if requested:
        unknown = [v for v in requested if v not in versions]
        if unknown:
            print(f"Unknown version(s): {', '.join(unknown)}", file=sys.stderr)
            print(f"Known: {', '.join(versions)}", file=sys.stderr)
            return 2
        versions = requested

    report = Report()
    for version in versions:
        verify_version(version, report)
    if not requested:
        verify_hosts(report)

    print()
    print(f"{report.checked} bound(s) checked.")
    if report.drift:
        print(f"{len(report.drift)} drifted:")
        for line in report.drift:
            print(f"  - {line}")
    if report.notes:
        print(f"{len(report.notes)} known source disagreement(s):")
        for line in report.notes:
            print(f"  - {line}")
    if report.errors:
        print(f"{len(report.errors)} source(s) unreadable:")
        for line in report.errors:
            print(f"  - {line}")
    if report.drift or report.errors:
        print("\nThe declared matrix was NOT modified. Update odoo_dwg/models.py")
        print("and docs/support-matrix.md together if the sources are right.")
        return 1
    print("No drift: every declared bound matches its source.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
