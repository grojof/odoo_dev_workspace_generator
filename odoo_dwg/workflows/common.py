"""Workflow pieces more than one menu uses: applying a previewed plan, and
redirecting a rehearsal database's mail to the local capture."""

from __future__ import annotations

from .. import egress, neutralise, planners
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
    state = mail_state(database, db_host, db_port, db_user)
    if state is None:
        return
    report_mail_state(database, state)


def mail_state(
    database: str, db_host: str, db_port: int, db_user: str
) -> egress.MailState | None:
    """What the database can do with mail, or None having said why not.

    Separate from the action that asks for a database, because the read-only
    `mail check` command needs the same reading without a prompt.
    """
    exists = "SELECT to_regclass('{}') IS NOT NULL"
    fetchmail = psql_scalar(exists.format("fetchmail_server"), database, db_host, db_port, db_user)
    captured = psql_scalar(
        exists.format(egress.CAPTURE_RECORD_TABLE), database, db_host, db_port, db_user
    )
    if fetchmail is None or captured is None:
        print(level_text("ERROR", tf("Could not read database {}.", database)))
        return None
    rows = psql_rows(
        egress.mail_state_sql(fetchmail=fetchmail == "t", captured=captured == "t"),
        database,
        db_host,
        db_port,
        db_user,
    )
    if rows is None:
        print(level_text("ERROR", tf("Could not read the mail configuration of {}.", database)))
        return None
    return egress.read_mail_state(rows)


def report_mail_state(database: str, state: egress.MailState) -> None:
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


# --- neutralising a copy of production ------------------------------------------------

def neutralise_database(db_host: str, db_port: int, db_user: str,
                        local_url: str = neutralise.DEFAULT_LOCAL_URL) -> None:
    """Keep a copy of production from acting on the outside, recording every change."""
    database = _database_to_act_on("Database to neutralise")
    if not database:
        return
    url = ask_text("URL this copy is reached at (its links will point here)", local_url)
    if not confirm_with_phrase(
        tf(
            "Every cron of {} but housekeeping will be switched off, its mail captured, and its "
            "tax, EDI, payment, delivery, OAuth, calendar and IAP integrations taken out of "
            "production. Every value changed is recorded inside the database; only 'Give a "
            "neutralised database its production settings back' puts them back.",
            database,
        ),
        "NEUTRALISE",
    ):
        print(level_text("INFO", t("Cancelled.")))
        return
    apply_if_confirmed(planners.plan_neutralise(database, db_host, db_port, db_user, url))


def restore_production(db_host: str, db_port: int, db_user: str) -> None:
    """Give production's recorded settings back: the step before a cutover, and
    never anything a flow does on its own."""
    database = _database_to_act_on("Database to give its production settings back")
    if not database:
        return
    later = later_rows(database, db_host, db_port, db_user)
    if later is None:
        return
    if later:
        print(level_text("WARN", tf(
            "{} row(s) did not exist in production and will stay neutralised:", str(len(later)))))
        for row in later:
            print(f"  {row.rule:<24} {row.relation} #{row.row_id} {row.xmlid}")
    if not confirm_with_phrase(
        tf(
            "{} will act on the outside again as production did: its crons run, its tax "
            "integration submits for real, its mail leaves through the client's servers. Do this "
            "on the day it goes into production, never on a copy being tested.",
            database,
        ),
        "RESTORE PRODUCTION",
    ):
        print(level_text("INFO", t("Cancelled.")))
        return
    apply_if_confirmed(planners.plan_restore_production(database, db_host, db_port, db_user))


def later_rows(database: str, db_host: str, db_port: int,
               db_user: str) -> list[neutralise.LaterRow] | None:
    """Rows a restore will leave off, or None having said why it cannot tell."""
    recorded = psql_scalar(f"SELECT to_regclass('{neutralise.RECORD_TABLE}') IS NOT NULL",
                           database, db_host, db_port, db_user)
    if recorded is None:
        print(level_text("ERROR", tf("Could not read database {}.", database)))
        return None
    if recorded != "t":
        print(level_text("INFO", tf("No neutralisation is recorded in {}.", database)))
        return None
    rows = psql_rows(neutralise.later_rows_sql(), database, db_host, db_port, db_user)
    if rows is None:
        print(level_text("ERROR", tf("Could not read database {}.", database)))
        return None
    return neutralise.read_later_rows(rows)


def armed_state(database: str, db_host: str, db_port: int,
                db_user: str) -> list[neutralise.Armed] | None:
    """What in the database can still act on the outside, by rule; None if unreadable."""
    columns = psql_rows(neutralise.columns_sql(), database, db_host, db_port, db_user)
    if columns is None:
        print(level_text("ERROR", tf("Could not read database {}.", database)))
        return None
    existing = {(row[0], row[1]) for row in columns if len(row) >= 2}
    rows = psql_rows(neutralise.check_sql(neutralise.applicable(existing)), database, db_host,
                     db_port, db_user)
    if rows is None:
        print(level_text("ERROR", tf("Could not read database {}.", database)))
        print(level_text("INFO", t(
            "The role may not be allowed to read every column the check needs (a read-only "
            "role that hides secrets cannot answer it); run it as the database's owner.")))
        return None
    return neutralise.read_armed(rows)


def report_armed(database: str, armed: list[neutralise.Armed],
                 mail: egress.MailState) -> bool:
    """The verdict, then what it rests on. True when something can act.

    A database with no active mail server is not counted as acting: Odoo then
    uses the configuration file's ``smtp_server``, and every configuration this
    tool writes points that at the capture. It is said, because a configuration
    written by someone else may not."""
    acting = bool(armed) or bool(mail.escaping)
    if not acting:
        print(level_text("OK", tf("Nothing in {} can act on the outside.", database)))
    else:
        print(level_text("WARN", tf("{} can still act on the outside:", database)))
        for item in armed:
            print(f"  {item.rule:<28} {item.count:>5}  {item.sample}")
        if mail.escaping:
            print("  " + t("mail: an active mail server points outside the capture"))
    if mail.falls_back_to_config:
        print(level_text("INFO", t(
            "No active mail server: Odoo uses the configuration file's smtp_server. The "
            "tool's own configurations point it at the capture; one written elsewhere may not.")))
    return acting


def check_neutralisation(db_host: str, db_port: int, db_user: str) -> None:
    """Whether a database can act on the outside. Reads only."""
    database = _database_to_act_on("Database to check")
    if not database:
        return
    armed = armed_state(database, db_host, db_port, db_user)
    mail = mail_state(database, db_host, db_port, db_user)
    if armed is None or mail is None:
        return
    if report_armed(database, armed, mail):
        print(level_text("INFO", t("Menu -> Neutralise a database turns it off.")))

