"""Entry point: language selection, the interactive menu, and the argparse CLI.

Run with no subcommand for the interactive menu; run a subcommand
(``workspace``/``provision``/``migrate``) for non-interactive use. Unlike its
sibling ``odoo_instance_manager``, this tool is **user-run** (it generates
workspaces under the user's home) and never requires root by itself; only
``provision apply`` may escalate for host-level changes, and it says so.
"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .i18n import set_language, t, tf
from .models import DEFAULT_DB_ROLE
from .prompts import choose, clear_screen
from .system import set_verbose
from .workflows import checks, migration_menu, provision_menu, workspace_menu

_LANG_ENV = "ODWG_LANG"


def _configure_utf8_console() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def _select_language(preferred: str | None = None) -> None:
    """Pick the UI language: explicit arg > ``ODWG_LANG`` > interactive prompt."""
    candidate = (preferred or os.environ.get(_LANG_ENV, "")).strip().lower()
    if candidate in {"en", "es"}:
        set_language(candidate)
        return
    lang = choose("Idioma / Language", ["English", "Español"], default_index=0)
    set_language("es" if lang == "Español" else "en")


def _print_banner() -> None:
    print(t("Odoo development & migration workspace generator"))
    print(t("- Generates and maintains per-client Odoo Community workspaces"))
    print(t("- Optional sections: system provisioning and migration (12→19)"))
    print(t("- Shows the command plan before running anything"))


def interactive_menu() -> int:
    clear_screen()
    _print_banner()

    while True:
        try:
            action = choose(
                "\nWhat do you want to do?",
                [
                    "Workspaces (create / manage)",
                    "System provisioning (optional)",
                    "Migration (OpenUpgrade 12→19)",
                    "Exit",
                ],
                default_index=None,
            )
        except (KeyboardInterrupt, EOFError):
            print(t("\nExiting."))
            return 0

        if not action:
            continue

        try:
            if action == "Workspaces (create / manage)":
                workspace_menu()
            elif action == "System provisioning (optional)":
                provision_menu()
            elif action == "Migration (OpenUpgrade 12→19)":
                migration_menu()
            elif action == "Exit":
                return 0
        except KeyboardInterrupt:
            print(t("\nOperation interrupted. Returning to the menu."))
            continue
        except EOFError:
            print(t("\nInput closed. Exiting."))
            return 0
        except (RuntimeError, ValueError, TypeError, OSError) as error:
            # A failed plan command (already reported by apply_commands), or
            # input the flows could not use — a malformed profile, an unreadable
            # file: report it and return to the menu instead of a traceback.
            print(tf("\n[ERROR] The operation did not complete: {}", error))
            continue


def _build_parser() -> argparse.ArgumentParser:
    # Shared options accepted both before and after the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    # SUPPRESS so a subparser's copy does not clobber a value given before the
    # subcommand; read it back with getattr(args, "lang", None).
    common.add_argument(
        "--lang",
        choices=["en", "es"],
        default=argparse.SUPPRESS,
        help="UI language (default: env/prompt).",
    )
    common.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
        help=t("Stream every line a plan's commands print (default: one line per step, "
               "plus warnings and the output of a step that fails). Also ODWG_VERBOSE=1."),
    )

    parser = argparse.ArgumentParser(
        prog="odoo-dwg",
        description=t("Odoo development & migration workspace generator"),
        parents=[common],
    )
    parser.add_argument("--version", action="version", version=f"odoo-dwg {__version__}")

    sub = parser.add_subparsers(dest="section")
    sub.add_parser("workspace", parents=[common],
                   help=t("Create / manage per-client workspaces."))
    sub.add_parser("provision", parents=[common], help=t("Prepare a Linux host (optional)."))

    # The read-only commands. They write nothing, prompt for nothing, and carry
    # their verdict in the exit code, so they are usable from a script and from a
    # second terminal while a migration runs. Everything that changes the host
    # stays in the menus, behind its confirmation phrase.
    migrate = sub.add_parser("migrate", parents=[common],
                             help=t("Run an OpenUpgrade migration (12→19)."))
    chain = argparse.ArgumentParser(add_help=False)
    chain.add_argument("--source", required=True, help=t("Source Odoo version (e.g. 12.0)."))
    chain.add_argument("--target", required=True, help=t("Target Odoo version (e.g. 19.0)."))
    migrate_actions = migrate.add_subparsers(dest="action")
    migrate_actions.add_parser(
        "report", parents=[common, chain],
        help=t("Print the cumulative run report. Writes nothing."))
    probes = migrate_actions.add_parser(
        "probes", parents=[common, chain],
        help=t("Report what each tester probe found in a database. Reads only."))
    probes.add_argument("--database", required=True, help=t("Database to read."))

    egress_parser = sub.add_parser("egress", parents=[common],
                                   help=t("Check the outbound firewall rules. Reads only."))
    egress_parser.add_subparsers(dest="action").add_parser(
        "check", parents=[common], help=t("Compare the host's rules with the tool's own."))

    mail = sub.add_parser("mail", parents=[common],
                          help=t("Check a database's outgoing mail. Reads only."))
    mail_check = mail.add_subparsers(dest="action").add_parser(
        "check", parents=[common], help=t("Report whether mail can leave a database."))
    mail_check.add_argument("--database", required=True, help=t("Database to read."))
    mail_check.add_argument("--db-host", default="127.0.0.1")
    mail_check.add_argument("--db-port", type=int, default=5432)
    mail_check.add_argument("--db-user", default=DEFAULT_DB_ROLE)
    return parser


def _language_from(argv: list[str] | None) -> str | None:
    """The `--lang` value, read before the parser exists.

    `--help` is printed by the parser itself, so the language has to be known
    before it is built or the help text can never be translated."""
    args = list(argv if argv is not None else sys.argv[1:])
    for index, item in enumerate(args):
        if item == "--lang" and index + 1 < len(args):
            return args[index + 1]
        if item.startswith("--lang="):
            return item.split("=", 1)[1]
    return os.environ.get("ODWG_LANG") or None


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_console()
    early = _language_from(argv)
    if early:
        set_language("es" if str(early).lower().startswith("es") else "en")
    parser = _build_parser()
    args = parser.parse_args(argv)
    lang = getattr(args, "lang", None)
    set_verbose(getattr(args, "verbose", False) or os.environ.get("ODWG_VERBOSE", "") == "1")

    if args.section is None:
        _select_language(lang)
        return interactive_menu()

    _select_language(lang)
    try:
        if args.section == "workspace":
            workspace_menu()
        elif args.section == "provision":
            provision_menu()
        elif args.section == "egress":
            return checks.egress_check()
        elif args.section == "mail":
            return checks.mail_check(
                args.database, args.db_host, args.db_port, args.db_user
            )
        elif args.section == "migrate":
            action = getattr(args, "action", None)
            if action == "report":
                return checks.migration_report(args.source, args.target)
            if action == "probes":
                return checks.probe_check(args.source, args.target, args.database)
            migration_menu()
    except (KeyboardInterrupt, EOFError):
        print(t("\nExiting."))
        return 0
    except (RuntimeError, ValueError, TypeError, OSError) as error:
        print(tf("\n[ERROR] The operation did not complete: {}", error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
