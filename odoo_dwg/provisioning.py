"""Provision-check facts and the pure capability-table logic (F2).

``gather_facts`` probes the host (I/O, via ``system``); ``provision_rows`` turns a
``ProvisionFacts`` into ``(state, capability, detail)`` rows for the check table —
pure, so it is unit-tested by injecting facts. Nothing here mutates the host;
installation lives in ``planners`` and is run by ``system.apply_commands``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import egress, planners, system
from .models import (
    DEFAULT_DB_ROLE,
    ODOO_SUPPORT,
    postgres_floor_for,
    python_tuple,
    supported_host,
    supported_hosts_text,
)


@dataclass
class ProvisionFacts:
    os_id: str = ""              # /etc/os-release ID, e.g. "ubuntu"
    os_version_id: str = ""      # /etc/os-release VERSION_ID, e.g. "24.04"
    os_codename: str = ""
    os_pretty_name: str = ""
    build_deps_missing: list[str] = field(default_factory=list)
    postgres_installed: bool = False
    postgres_running: bool = False
    dev_role: str = DEFAULT_DB_ROLE
    # None: it could not be told without a password prompt.
    dev_role_exists: bool | None = False
    postgres_version: int | None = None
    wkhtmltopdf: str | None = None
    node: bool = False
    rtlcss: bool = False
    uv: bool = False
    uv_pythons: list[str] = field(default_factory=list)
    host_python: str | None = None
    # Odoo versions this check is scoped to, which set the PostgreSQL floor.
    versions: list[str] = field(default_factory=list)
    # Optional egress control and mail capture.
    opensnitch_version: str | None = None
    opensnitch_active: bool = False
    # Hardened settings the running config does not have (``key: value``).
    opensnitch_deviations: list[str] = field(default_factory=list)
    mailpit_version: str | None = None
    mailpit_active: bool = False
    # Non-loopback DNS servers, for the baseline rules.
    resolvers: list[str] = field(default_factory=list)


def gather_facts(dev_role: str = DEFAULT_DB_ROLE, versions: list[str] | None = None) -> ProvisionFacts:
    """Probe the host for readiness (I/O). ``versions`` scopes the PostgreSQL
    floor to the Odoo versions in play; empty means every supported version."""
    release = system.detect_os_release()
    running = system.postgres_running()
    # Not running: the role cannot be told apart from an unreachable server.
    role_exists = system.db_role_exists(dev_role) if running else None
    uv_present = system.has_tool("uv")
    # Both packages matter: with only the daemon installed, the UI must still be.
    opensnitch_version = system.deb_version("opensnitch")
    if opensnitch_version and not system.deb_version("python3-opensnitch-ui"):
        opensnitch_version = None
    return ProvisionFacts(
        os_id=release.get("ID", ""),
        os_version_id=release.get("VERSION_ID", ""),
        os_codename=release.get("VERSION_CODENAME", ""),
        os_pretty_name=release.get("PRETTY_NAME", ""),
        build_deps_missing=[p for p in planners.BUILD_DEPS if not system.package_installed(p)],
        postgres_installed=system.postgres_installed(),
        postgres_running=running,
        postgres_version=system.detect_postgres_version() if running else None,
        dev_role=dev_role,
        dev_role_exists=role_exists,
        wkhtmltopdf=system.wkhtmltopdf_version(),
        node=system.has_tool("node") or system.has_tool("nodejs"),
        rtlcss=system.has_tool("rtlcss"),
        uv=uv_present,
        uv_pythons=system.uv_python_minors() if uv_present else [],
        host_python=system.detect_python_version(),
        versions=list(versions or []),
        opensnitch_version=opensnitch_version,
        opensnitch_active=system.service_active("opensnitch") if opensnitch_version else False,
        opensnitch_deviations=_opensnitch_deviations() if opensnitch_version else [],
        mailpit_version=system.mailpit_version(egress.MAILPIT_BINARY),
        mailpit_active=system.service_active("mailpit"),
        resolvers=egress.parse_resolvers(system.read_text("/etc/resolv.conf") or ""),
    )


def _postgres_version_rows(facts: ProvisionFacts) -> list[tuple[str, str, str]]:
    """The installed server version against the floor the matrix declares for the
    versions in play. Pure; no row at all when there is nothing to compare."""
    if facts.postgres_version is None:
        return []
    scoped = facts.versions or [ODOO_SUPPORT[major].version for major in sorted(ODOO_SUPPORT)]
    floor = postgres_floor_for(scoped)
    installed = str(facts.postgres_version)
    if floor is None:
        return [("INFO", "PostgreSQL version", f"{installed} (no version declares a floor)")]
    required, version = floor
    if python_tuple(installed) < python_tuple(required):
        return [
            (
                "WARN",
                "PostgreSQL version",
                f"{installed} is below the {required} Odoo {version} requires",
            )
        ]
    return [("OK", "PostgreSQL version", f"{installed} (Odoo {version} requires {required})")]


def _opensnitch_deviations() -> list[str]:
    text = system.read_text(egress.OPENSNITCH_CONFIG)
    if text is None:
        return ["config: unreadable"]
    try:
        return egress.config_deviations(json.loads(text))
    except ValueError:
        return ["config: not valid JSON"]


def _egress_rows(facts: ProvisionFacts) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    label = "Egress firewall — OpenSnitch (optional)"
    if not facts.opensnitch_version:
        rows.append(("INFO", label, "not installed"))
    elif not facts.opensnitch_active:
        rows.append(("WARN", label, f"{facts.opensnitch_version} installed but not running"))
    elif facts.opensnitch_deviations:
        softened = ", ".join(facts.opensnitch_deviations)
        rows.append(("WARN", label, f"{facts.opensnitch_version} running, not hardened: {softened}"))
    else:
        rows.append(("OK", label, f"{facts.opensnitch_version} running, hardened (default deny)"))
    label = "Mail capture — Mailpit (optional)"
    if not facts.mailpit_version:
        rows.append(("INFO", label, "not installed"))
    elif facts.mailpit_active:
        rows.append(("OK", label, f"{facts.mailpit_version} running — SMTP 127.0.0.1:1025, UI :8025"))
    else:
        rows.append(("WARN", label, f"{facts.mailpit_version} installed but not running"))
    return rows


def provision_rows(facts: ProvisionFacts) -> list[tuple[str, str, str]]:
    """Pure: map facts to (state, capability, detail) rows (state ∈ OK/WARN/MISSING/INFO)."""
    rows: list[tuple[str, str, str]] = []

    host = supported_host(facts.os_id, facts.os_version_id)
    if host is not None:
        detail = host.name + (f" ({host.codename})" if host.codename else "")
        rows.append(("OK", "Host release", detail))
    else:
        detected = facts.os_pretty_name or f"{facts.os_id or 'unknown'} {facts.os_version_id}".strip()
        rows.append(
            (
                "WARN",
                "Host release",
                f"{detected} is not supported — supported: {supported_hosts_text()}",
            )
        )

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

    rows += _postgres_version_rows(facts)

    if facts.dev_role_exists:
        rows.append(("OK", f"Dev role ({facts.dev_role})", "present"))
    elif facts.dev_role_exists is None:
        detail = ("could not be checked: PostgreSQL is not running" if not facts.postgres_running
                  else "could not be checked without sudo — run with sudo, or log in as the role once")
        rows.append(("WARN", f"Dev role ({facts.dev_role})", detail))
    else:
        rows.append(("MISSING", f"Dev role ({facts.dev_role})", "not found"))

    if not facts.wkhtmltopdf:
        rows.append(("MISSING", "wkhtmltopdf", "not installed — PDF reports will fail"))
    elif "with patched qt" in facts.wkhtmltopdf.lower():
        rows.append(("OK", "wkhtmltopdf", facts.wkhtmltopdf))
    else:
        rows.append(("WARN", "wkhtmltopdf", f"{facts.wkhtmltopdf} (un-patched — reports may be degraded)"))

    rows.append(("OK" if facts.node else "INFO", "Node.js (optional)", "present" if facts.node else "not installed (only for right-to-left languages)"))
    rows.append(("OK" if facts.rtlcss else "INFO", "rtlcss (optional)", "present" if facts.rtlcss else "not installed (only for right-to-left languages)"))

    if facts.uv:
        provides = ", ".join(facts.uv_pythons) if facts.uv_pythons else "no interpreters listed"
        rows.append(("OK", "uv (interpreters)", f"present — provides {provides}"))
    else:
        rows.append(
            (
                "INFO",
                "uv (interpreters)",
                "not installed (needed for migration steps and for any Odoo version "
                "the host python3 is out of range for — docs.astral.sh/uv)",
            )
        )

    if facts.host_python:
        rows.append(("INFO", "Host python3", facts.host_python))

    rows += _egress_rows(facts)
    return rows
