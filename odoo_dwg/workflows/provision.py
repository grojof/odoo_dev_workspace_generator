"""Section 1 — System provisioning (optional, host-agnostic).

Prepares a *Linux* host for Odoo development: `check` reports host readiness
(read-only), and `apply` installs/configures the missing capabilities (apt build
deps, PostgreSQL + dev role, patched wkhtmltopdf, optional rtlcss for right-to-left languages) via
plan → preview → apply. `apply` requires root and refuses any host outside the
releases the support matrix declares. Never assumes WSL.
"""

from __future__ import annotations

import os

from .. import egress, planners, provisioning, system
from ..i18n import t, tf
from ..models import DB_ROLE_RE, DEFAULT_DB_ROLE, supported_host, supported_hosts_text
from ..prompts import ask_bool, ask_text, choose, confirm_with_phrase
from ..system import apply_commands, preview_commands
from ..ui import level_text, render_table

# The wkhtmltopdf version is the same (0.12.6) for every supported dev major
# (>= 15); use 18 as the representative dev target for the host-level install.
_DEV_WKHTMLTOPDF_MAJOR = 18


def _is_root() -> bool:
    # geteuid is absent on Windows; the tool provisions on Linux only.
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _check() -> None:
    facts = provisioning.gather_facts()
    rows = [list(row) for row in provisioning.provision_rows(facts)]
    print(render_table(["State", "Capability", "Detail"], rows))


def _apply() -> None:
    if not _is_root():
        print(level_text("ERROR", t("To apply system changes, run with privileges (sudo).")))
        return

    role = ask_text("Development PostgreSQL role", DEFAULT_DB_ROLE, required=True)
    # The role reaches SQL run as postgres: refuse anything but a plain identifier.
    if not DB_ROLE_RE.fullmatch(role):
        print(level_text("ERROR", tf("Invalid PostgreSQL role: {}", role)))
        return
    facts = provisioning.gather_facts(dev_role=role)

    # Refuse before assembling any command: this host is not one the project
    # supports, so its packages are nothing we make a claim about.
    host = supported_host(facts.os_id, facts.os_version_id)
    if host is None:
        detected = facts.os_pretty_name or f"{facts.os_id or 'unknown'} {facts.os_version_id}".strip()
        print(
            level_text(
                "ERROR",
                tf(
                    "{} is not supported — supported hosts: {}.",
                    detected,
                    supported_hosts_text(),
                ),
            )
        )
        return

    commands: list = []
    if facts.build_deps_missing:
        commands += planners.plan_build_deps()
    # Every probe is a tri-state: False and None both mean "do the work". A
    # stopped server hides the role and pg_hba behind None, and skipping on that
    # would report a host as provisioned that has no role at all.
    if (not facts.postgres_installed or not facts.postgres_running
            or facts.dev_role_exists is not True):
        commands += planners.plan_postgresql(role)
    elif facts.pg_hba_blanket_trust is not False or facts.pg_hba_role_trusted is not True:
        # PostgreSQL and the role are already there, but the loopback rules are
        # not the ones this tool wants (or could not be read): narrow them.
        commands += planners.plan_pg_hba_trust(role)
    if not facts.wkhtmltopdf or "with patched qt" not in facts.wkhtmltopdf.lower():
        wkhtmltopdf = planners.plan_wkhtmltopdf(_DEV_WKHTMLTOPDF_MAJOR, facts.os_codename)
        if not wkhtmltopdf:
            print(level_text("WARN", tf(
                "No verified patched wkhtmltopdf is pinned for {} — install it by hand "
                "(github.com/wkhtmltopdf/packaging) or PDF reports will be degraded.",
                facts.os_codename or "this host",
            )))
        commands += wkhtmltopdf
    if ask_bool(
        "Install rtlcss (with Node.js)? Only needed if users work in a right-to-left language (Arabic, Hebrew, Persian…)",
        False,
    ):
        commands += planners.plan_node_rtlcss()
    commands += _optional_egress(facts)

    if not commands:
        print(level_text("OK", t("Host already provisioned — nothing to do.")))
        return

    preview_commands(commands)
    if ask_bool("Apply this plan now?", False):
        apply_commands(commands)
        print(level_text("OK", t("Provisioning applied.")))
        _report_services()


def _report_services() -> None:
    """What the services are actually doing, once the plan says it is done.

    `systemctl restart` returns as soon as a `Type=simple` unit is forked, so a
    daemon that dies a second later leaves every step reporting success. Both of
    these are security-relevant when they are not running — the firewall most of
    all — so the state is read back rather than assumed."""
    opensnitch, firewall_on, mailpit, capture_on = _egress_status()
    if not opensnitch and not mailpit:
        return
    rows = []
    if opensnitch:
        rows.append(["OpenSnitch", opensnitch, t("running") if firewall_on else t("NOT running")])
    if mailpit:
        rows.append(["Mailpit", mailpit, t("running") if capture_on else t("NOT running")])
    print(render_table(["Component", "Version", "State"], rows))
    if (opensnitch and not firewall_on) or (mailpit and not capture_on):
        print(level_text("WARN", t(
            "A service is installed but not running. Check `systemctl status` for it: a unit that "
            "starts and then exits still leaves its install step reporting success."
        )))


def _optional_egress(facts: provisioning.ProvisionFacts) -> list:
    """The opt-in outbound firewall and mail capture (docs/host/egress-control.md)."""
    commands: list = []
    print(
        level_text(
            "INFO",
            t(
                "OpenSnitch blocks every outbound connection without a rule, asking in its UI "
                "when it is open. Odoo may reach only localhost, plus DNS on port 53; the "
                "development tools keep their hosts. See docs/host/egress-control.md."
            ),
        )
    )
    if ask_bool("Install or update the outbound firewall (OpenSnitch)?", False):
        commands += planners.plan_opensnitch(facts.resolvers, facts.opensnitch_version)
    if ask_bool("Install or update the local mail capture (Mailpit)?", False):
        commands += planners.plan_mailpit(facts.mailpit_version)
    return commands


def _egress_status() -> tuple[str | None, bool, str | None, bool]:
    opensnitch = system.deb_version("opensnitch")
    mailpit = system.mailpit_version(egress.MAILPIT_BINARY)
    return (
        opensnitch,
        bool(opensnitch) and system.service_active("opensnitch"),
        mailpit,
        bool(mailpit) and system.service_active("mailpit"),
    )


def _uninstall_opensnitch() -> None:
    removed = system.apt_purge_removals(planners.OPENSNITCH_PACKAGE_NAMES)
    print(level_text("INFO", tf("apt would remove {} package(s): {}", len(removed), ", ".join(removed))))
    print(level_text("INFO", tf("Your own rules in {} are kept.", egress.OPENSNITCH_RULES_DIR)))
    if not confirm_with_phrase(t("This removes the outbound firewall."), "UNINSTALL"):
        print(level_text("INFO", t("Cancelled.")))
        return
    _preview_and_apply(planners.plan_opensnitch_uninstall())


def _uninstall_mailpit() -> None:
    if not confirm_with_phrase(
        t("This removes Mailpit and every message it captured."), "UNINSTALL"
    ):
        print(level_text("INFO", t("Cancelled.")))
        return
    _preview_and_apply(planners.plan_mailpit_uninstall())


def _preview_and_apply(commands: list) -> None:
    preview_commands(commands)
    if ask_bool("Apply this plan now?", False):
        apply_commands(commands)
        print(level_text("OK", t("Done.")))


def _egress_menu() -> None:
    """Turn the outbound firewall and the mail capture on or off, or uninstall them."""
    if not _is_root():
        print(level_text("ERROR", t("To apply system changes, run with privileges (sudo).")))
        return
    while True:
        opensnitch, firewall_on, mailpit, capture_on = _egress_status()
        rows = [
            ["OpenSnitch", opensnitch or t("not installed"),
             t("on") if firewall_on else t("off")],
            ["Mailpit", mailpit or t("not installed"), t("on") if capture_on else t("off")],
        ]
        print(render_table(["Component", "Version", "State"], rows))
        options: list[str] = []
        if opensnitch:
            options.append("Turn the outbound firewall off" if firewall_on
                           else "Turn the outbound firewall on")
            options.append("Uninstall the outbound firewall")
        if mailpit:
            options.append("Turn the mail capture off" if capture_on else "Turn the mail capture on")
            options.append("Uninstall the mail capture")
        if not options:
            print(level_text("INFO", t("Neither is installed — use Apply to install them.")))
            return
        action = choose("\nOutbound firewall and mail capture", options + ["Back"], default_index=None)
        if action in ("", "Back"):
            return
        if action == "Turn the outbound firewall off":
            _preview_and_apply(planners.plan_service_switch("opensnitch", on=False))
        elif action == "Turn the outbound firewall on":
            _preview_and_apply(planners.plan_service_switch("opensnitch", on=True))
        elif action == "Uninstall the outbound firewall":
            _uninstall_opensnitch()
        elif action == "Turn the mail capture off":
            _preview_and_apply(planners.plan_service_switch("mailpit", on=False))
        elif action == "Turn the mail capture on":
            _preview_and_apply(planners.plan_service_switch("mailpit", on=True))
        elif action == "Uninstall the mail capture":
            _uninstall_mailpit()


def provision_menu() -> None:
    while True:
        action = choose(
            "\nSystem provisioning",
            [
                "Check host readiness",
                "Apply (install what's missing)",
                "Outbound firewall and mail capture (on/off, uninstall)",
                "Back",
            ],
            default_index=None,
        )
        if action in ("", "Back"):
            return
        if action == "Check host readiness":
            _check()
        elif action == "Apply (install what's missing)":
            _apply()
        elif action == "Outbound firewall and mail capture (on/off, uninstall)":
            _egress_menu()
