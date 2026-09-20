"""Workflow pieces more than one menu uses: applying a previewed plan, and
redirecting a rehearsal database's mail to the local capture."""

from __future__ import annotations

from .. import egress, planners
from ..i18n import t, tf
from ..models import DB_NAME_RE
from ..prompts import ask_bool, ask_text, confirm_with_phrase
from ..system import apply_commands, preview_commands, psql_rows, psql_scalar
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

def _database_to_act_on(prompt: str) -> str:
    """A database name from the operator, refused unless PostgreSQL would accept
    it: it reaches a shell and a connection string."""
    database = ask_text(prompt, required=True)
    if not DB_NAME_RE.fullmatch(database):
        print(level_text("ERROR", tf("Invalid database name: {}", database)))
        return ""
    return database


def capture_mail(db_host: str, db_port: int, db_user: str) -> None:
    """Stop a database's mail leaving, without altering what it has configured."""
    database = _database_to_act_on("Database whose mail to capture")
    if not database:
        return
    if not confirm_with_phrase(
        tf(
            "The mail servers of {} will be deactivated and one pointing at Mailpit added. "
            "Nothing configured is overwritten: 'Restore the mail configuration' gives this "
            "database back exactly what it has now.",
            database,
        ),
        "CAPTURE",
    ):
        print(level_text("INFO", t("Cancelled.")))
        return
    apply_if_confirmed(planners.plan_mail_capture(database, db_host, db_port, db_user))


def restore_mail(db_host: str, db_port: int, db_user: str) -> None:
    """Give a captured database back the mail configuration it had — the step that
    makes a migrated database fit to go into production."""
    database = _database_to_act_on("Database whose mail configuration to restore")
    if not database:
        return
    if not confirm_with_phrase(
        tf(
            "{} will mail out again through the servers it had before the capture. Do this "
            "when the database is going into production, not while it is still being "
            "rehearsed.",
            database,
        ),
        "RESTORE",
    ):
        print(level_text("INFO", t("Cancelled.")))
        return
    apply_if_confirmed(planners.plan_mail_restore(database, db_host, db_port, db_user))


def check_mail(db_host: str, db_port: int, db_user: str) -> None:
    """Report whether mail can leave this database. Reads only."""
    database = _database_to_act_on("Database whose mail to check")
    if not database:
        return
    exists = "SELECT to_regclass('{}') IS NOT NULL"
    fetchmail = psql_scalar(exists.format("fetchmail_server"), database, db_host, db_port, db_user)
    captured = psql_scalar(
        exists.format(egress.CAPTURE_RECORD_TABLE), database, db_host, db_port, db_user
    )
    if fetchmail is None or captured is None:
        print(level_text("ERROR", tf("Could not read database {}.", database)))
        return
    rows = psql_rows(
        egress.mail_state_sql(fetchmail=fetchmail == "t", captured=captured == "t"),
        database,
        db_host,
        db_port,
        db_user,
    )
    if rows is None:
        print(level_text("ERROR", tf("Could not read the mail configuration of {}.", database)))
        return
    _report_mail_state(database, egress.read_mail_state(rows))


def _report_mail_state(database: str, state: egress.MailState) -> None:
    """The verdict first, then what it rests on: the question is whether mail can
    leave, and a table of servers does not answer it by itself."""
    if state.escaping:
        print(level_text("WARN", tf("Mail can leave {}.", database)))
    elif state.falls_back_to_config:
        print(
            level_text(
                "INFO",
                tf(
                    "{} has no active mail server: Odoo will use the smtp_server of its "
                    "configuration file, whatever that points at.",
                    database,
                ),
            )
        )
    else:
        print(level_text("OK", tf("Mail cannot leave {}.", database)))
    if state.captured:
        print(
            level_text(
                "INFO",
                tf("A capture is in effect: {} mail server(s) deactivated, not lost.",
                   str(state.deactivated)),
            )
        )
    for server in state.servers:
        mark = "*" if server.active else " "
        suffix = t(" — the capture") if server.is_capture else ""
        print(f"  {mark} {server.name} → {server.host}:{server.port}{suffix}")
    if state.fetchmail_active:
        print(
            level_text(
                "WARN",
                tf("{} fetchmail server(s) are still fetching.", str(state.fetchmail_active)),
            )
        )
