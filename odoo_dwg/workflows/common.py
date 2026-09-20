"""Workflow pieces more than one menu uses: applying a previewed plan, and
redirecting a rehearsal database's mail to the local capture."""

from __future__ import annotations

from .. import planners
from ..i18n import t, tf
from ..models import DB_NAME_RE
from ..prompts import ask_bool, ask_text, confirm_with_phrase
from ..system import apply_commands, preview_commands
from ..ui import level_text


def apply_if_confirmed(commands: list) -> bool:
    """Preview, confirm and apply. True only when the plan ran to completion
    (a failing command raises from apply_commands)."""
    if not commands:
        print(level_text("INFO", t("Nothing to do.")))
        return False
    preview_commands(commands)
    if ask_bool("Apply this plan now?", False):
        apply_commands(commands)
        return True
    return False

def redirect_mail(db_host: str, db_port: int, db_user: str) -> None:
    """Point a rehearsal database's mail servers at Mailpit (workspace and migration menus)."""
    database = ask_text("Database whose mail to redirect", required=True)
    if not DB_NAME_RE.fullmatch(database):
        print(level_text("ERROR", tf("Invalid database name: {}", database)))
        return
    if not confirm_with_phrase(
        tf(
            "Every mail server of {} will point at Mailpit and lose its credentials, and mail "
            "fetching stops. Use it on rehearsal copies only — never on a database going back "
            "to production.",
            database,
        ),
        "REDIRECT",
    ):
        print(level_text("INFO", t("Cancelled.")))
        return
    apply_if_confirmed(planners.plan_mail_redirect(database, db_host, db_port, db_user))
