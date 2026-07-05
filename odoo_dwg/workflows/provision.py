"""Section 1 — System provisioning (optional, host-agnostic).

Prepares a *Linux* host for Odoo development/migration (PostgreSQL + role,
wkhtmltopdf, Node + rtlcss, per-version Python interpreters). Never assumes WSL.
F0 stub: navigable menu only. F2 implements ``check`` (report what's missing) and
``apply`` (install what's missing) as independent capabilities.
"""

from __future__ import annotations

from ..i18n import t
from ..ui import level_text


def provision_menu() -> None:
    print(level_text("INFO", t("(not implemented yet)")))
