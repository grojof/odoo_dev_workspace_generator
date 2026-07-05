"""Section 2 — Workspaces (create / manage). Core value of the tool.

F0 stub: navigable menu only. F1 implements profile → workspace layout (shared
repo cache, per-instance venv, addons-custom/addons-oca, per-version odoo.conf,
VSCode files, and a robust per-workspace README).
"""

from __future__ import annotations

from ..i18n import t
from ..ui import level_text


def workspace_menu() -> None:
    print(level_text("INFO", t("(not implemented yet)")))
