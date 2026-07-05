"""Provision-check facts and the pure capability-table logic (F2).

``gather_facts`` probes the host (I/O, via ``system``); ``provision_rows`` turns a
``ProvisionFacts`` into ``(state, capability, detail)`` rows for the check table —
pure, so it is unit-tested by injecting facts. Nothing here mutates the host;
installation lives in ``planners`` and is run by ``system.apply_commands``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import planners, system


@dataclass
class ProvisionFacts:
    os_family: str = ""          # "debian" when apt-family, else "" (unsupported)
    os_codename: str = ""
    build_deps_missing: list[str] = field(default_factory=list)
    postgres_installed: bool = False
    postgres_running: bool = False
    dev_role: str = "odoo"
    dev_role_exists: bool = False
    wkhtmltopdf: str | None = None
    node: bool = False
    rtlcss: bool = False


def gather_facts(dev_role: str = "odoo") -> ProvisionFacts:
    """Probe the host for readiness (I/O)."""
    release = system.detect_os_release()
    family = system.apt_family()
    role_exists = system.db_role_exists(dev_role) if system.postgres_running() else False
    return ProvisionFacts(
        os_family=family,
        os_codename=release.get("VERSION_CODENAME", ""),
        build_deps_missing=[p for p in planners.BUILD_DEPS if not system.package_installed(p)],
        postgres_installed=system.postgres_installed(),
        postgres_running=system.postgres_running(),
        dev_role=dev_role,
        dev_role_exists=role_exists,
        wkhtmltopdf=system.wkhtmltopdf_version(),
        node=system.has_tool("node") or system.has_tool("nodejs"),
        rtlcss=system.has_tool("rtlcss"),
    )


def provision_rows(facts: ProvisionFacts) -> list[tuple[str, str, str]]:
    """Pure: map facts to (state, capability, detail) rows (state ∈ OK/WARN/MISSING/INFO)."""
    rows: list[tuple[str, str, str]] = []

    if facts.os_family == "debian":
        rows.append(("OK", "Package family", f"Debian/Ubuntu (apt){' — ' + facts.os_codename if facts.os_codename else ''}"))
    else:
        rows.append(("WARN", "Package family", "unsupported — only the Debian/Ubuntu (apt) family is supported"))

    if not facts.build_deps_missing:
        rows.append(("OK", "Odoo build dependencies", "all present"))
    else:
        rows.append(("MISSING", "Odoo build dependencies", f"{len(facts.build_deps_missing)} missing"))

    if not facts.postgres_installed:
        rows.append(("MISSING", "PostgreSQL", "not installed"))
    elif facts.postgres_running:
        rows.append(("OK", "PostgreSQL", "installed and running"))
    else:
        rows.append(("WARN", "PostgreSQL", "installed but not running"))

    if facts.dev_role_exists:
        rows.append(("OK", f"Dev role ({facts.dev_role})", "present"))
    else:
        rows.append(("MISSING", f"Dev role ({facts.dev_role})", "not found"))

    if not facts.wkhtmltopdf:
        rows.append(("MISSING", "wkhtmltopdf", "not installed — PDF reports will fail"))
    elif "with patched qt" in facts.wkhtmltopdf.lower():
        rows.append(("OK", "wkhtmltopdf", facts.wkhtmltopdf))
    else:
        rows.append(("WARN", "wkhtmltopdf", f"{facts.wkhtmltopdf} (un-patched — reports may be degraded)"))

    rows.append(("OK" if facts.node else "INFO", "Node.js (optional)", "present" if facts.node else "not installed (only needed for RTL/less)"))
    rows.append(("OK" if facts.rtlcss else "INFO", "rtlcss (optional)", "present" if facts.rtlcss else "not installed (only needed for RTL/less)"))

    return rows
