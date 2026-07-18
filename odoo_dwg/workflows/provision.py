"""Section 1 — System provisioning (optional, host-agnostic).

Prepares a *Linux* host for Odoo development: `check` reports host readiness
(read-only), and `apply` installs/configures the missing capabilities (apt build
deps, PostgreSQL + dev role, patched wkhtmltopdf, optional Node + rtlcss) via
plan → preview → apply. `apply` requires root and targets the Debian/Ubuntu (apt)
family only. Never assumes WSL.
"""

from __future__ import annotations

import os

from .. import planners, provisioning
from ..i18n import t
from ..prompts import ask_bool, ask_text, choose
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

    role = ask_text("Development PostgreSQL role", "odoo", required=True)
    facts = provisioning.gather_facts(dev_role=role)

    if facts.os_family != "debian":
        print(level_text("ERROR", t("Only the Debian/Ubuntu (apt) family is supported.")))
        return

    commands: list = []
    if facts.build_deps_missing:
        commands += planners.plan_build_deps()
    if not facts.postgres_installed or not facts.dev_role_exists:
        commands += planners.plan_postgresql(role)
    if not facts.wkhtmltopdf or "with patched qt" not in facts.wkhtmltopdf.lower():
        commands += planners.plan_wkhtmltopdf(_DEV_WKHTMLTOPDF_MAJOR, facts.os_codename)
    if ask_bool("Also install the optional web toolchain (Node + rtlcss)?", False):
        commands += planners.plan_node_rtlcss()
    if not facts.docker_daemon and ask_bool(
        "Install Docker Engine? (only needed for Odoo 12/13 migration steps)", False
    ):
        commands += planners.plan_docker_engine()
    if ask_bool("Pull the OpenUpgrade fallback images (odoo:13.0, odoo:12.0)?", False):
        commands += planners.plan_pull_openupgrade_images()

    if not commands:
        print(level_text("OK", t("Host already provisioned — nothing to do.")))
        return

    preview_commands(commands)
    if ask_bool("Apply this plan now?", False):
        apply_commands(commands)
        print(level_text("OK", t("Provisioning applied.")))


def provision_menu() -> None:
    while True:
        action = choose(
            "\nSystem provisioning",
            ["Check host readiness", "Apply (install what's missing)", "Back"],
            default_index=None,
        )
        if action in ("", "Back"):
            return
        if action == "Check host readiness":
            _check()
        elif action == "Apply (install what's missing)":
            _apply()
