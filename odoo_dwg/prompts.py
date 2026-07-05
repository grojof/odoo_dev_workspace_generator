"""Interactive input primitives (mirrors ``odoo_instance_manager``).

Every prompt routes its labels through the i18n layer, and ``choose`` renders a
numbered menu with a consistent ``0)`` cancel entry. Standard-library only.
"""

from __future__ import annotations

import getpass
import os
from pathlib import Path

from .i18n import current_language, t, tf
from .ui import level_text, prompt_label, style, title

_last_selected_dir: Path | None = None


def _remember_directory_from_path(raw_path: str) -> None:
    global _last_selected_dir
    candidate = Path(raw_path).expanduser()
    candidate_dir = candidate if candidate.is_dir() else candidate.parent
    if candidate_dir.exists() and candidate_dir.is_dir():
        _last_selected_dir = candidate_dir.resolve()


def ask_text(label: str, default: str | None = None, required: bool = False) -> str:
    while True:
        suffix = f" [{default}]" if default is not None else ""
        value = input(f"{prompt_label(label)}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        if not required:
            return ""
        print(level_text("ERROR", "Value is required."))


def ask_int(label: str, default: int, min_value: int = 1, max_value: int = 65535) -> int:
    while True:
        raw = ask_text(label, str(default), required=True)
        try:
            value = int(raw)
        except ValueError:
            print(level_text("ERROR", "Must be an integer."))
            continue
        if min_value <= value <= max_value:
            return value
        print(level_text("ERROR", tf("Value out of range ({}-{}).", min_value, max_value)))


def ask_port(label: str, default: int) -> int:
    return ask_int(label, default, min_value=1, max_value=65535)


def ask_secret(label: str, required: bool = True) -> str:
    """Prompt for a secret without echoing it to the screen (via getpass)."""
    while True:
        value = getpass.getpass(f"{prompt_label(label)}: ").strip()
        if value:
            return value
        if not required:
            return ""
        print(level_text("ERROR", "Value is required."))


def ask_bool(label: str, default: bool = True) -> bool:
    yes_letter = "S" if current_language() == "es" else "Y"
    marker = f"{yes_letter}/n" if default else f"{yes_letter.lower()}/N"
    affirmative = {"y", "yes", "s", "si", "sí"}
    negative = {"n", "no"}
    while True:
        raw = input(f"{prompt_label(label)} ({style(marker, 'dim')}): ").strip().lower()
        if not raw:
            return default
        if raw in affirmative:
            return True
        if raw in negative:
            return False
        print(level_text("ERROR", "Answer 'yes'/'y' or 'no'/'n' (Enter = default)."))


def choose(label: str, options: list[str], default_index: int | None = None) -> str:
    """Render a numbered menu with a consistent ``0)`` cancel entry.

    If ``options`` already contains a cancel-like entry (``Cancel``/``Back``/
    ``Exit``), that is the ``0`` option and selecting it returns that string.
    Otherwise a synthetic ``0) Cancel`` is shown and selecting it (or pressing
    Enter with no default) returns ``""`` — the sentinel every caller treats as
    "cancelled". Options are shown translated but the ORIGINAL (English) string
    is returned, so caller comparisons keep working.
    """
    print(title(label))
    zero_candidates = ["Cancel", "Back", "Exit"]
    zero_option = next((item for item in zero_candidates if item in options), None)
    zero_label = zero_option if zero_option is not None else "Cancel"

    indexed_options = [option for option in options if option != zero_option]

    print(f"  {style('0)', 'blue', 'bold')} {t(zero_label)}")

    for index, option in enumerate(indexed_options, start=1):
        default_tag = (
            " (default)"
            if default_index is not None and options[default_index] == option
            else ""
        )
        marker = style(f"{index})", "blue", "bold")
        print(f"  {marker} {t(option)}{style(default_tag, 'dim')}")

    while True:
        raw = input(f"{prompt_label('Select an option')}: ").strip()
        if raw == "0":
            return zero_option if zero_option is not None else ""

        if not raw:
            if default_index is not None:
                return options[default_index]
            print(level_text("INFO", "No selection (0 to cancel)."))
            return ""
        try:
            selected = int(raw)
        except ValueError:
            print(level_text("ERROR", "Enter the option number."))
            continue
        if 1 <= selected <= len(indexed_options):
            return indexed_options[selected - 1]
        print(level_text("ERROR", "Option out of range."))


def clear_screen() -> None:
    command = "cls" if os.name == "nt" else "clear"
    os.system(command)


def confirm_with_phrase(label: str, phrase: str) -> bool:
    print(title(label))
    value = input(
        f"{prompt_label('Type exactly')} {style(phrase, 'magenta', 'bold')} "
        f"{prompt_label('to confirm')}: "
    ).strip()
    return value == phrase
