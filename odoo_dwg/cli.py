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
from .prompts import choose, clear_screen
from .workflows import migration_menu, provision_menu, workspace_menu

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

    parser = argparse.ArgumentParser(
        prog="odoo-dwg",
        description=t("Odoo development & migration workspace generator"),
        parents=[common],
    )
    parser.add_argument("--version", action="version", version=f"odoo-dwg {__version__}")

    sub = parser.add_subparsers(dest="section")
    sub.add_parser("workspace", parents=[common], help="Create / manage per-client workspaces.")
    sub.add_parser("provision", parents=[common], help="Prepare a Linux host (optional).")
    sub.add_parser("migrate", parents=[common], help="Run an OpenUpgrade migration (12→19).")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_console()
    parser = _build_parser()
    args = parser.parse_args(argv)
    lang = getattr(args, "lang", None)

    if args.section is None:
        _select_language(lang)
        return interactive_menu()

    _select_language(lang)
    try:
        if args.section == "workspace":
            workspace_menu()
        elif args.section == "provision":
            provision_menu()
        elif args.section == "migrate":
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
