"""Interactive input primitives (mirrors ``odoo_instance_manager``).

Every prompt routes its labels through the i18n layer, and ``choose`` renders a
numbered menu with a consistent ``0)`` cancel entry. Standard-library only.
"""

from __future__ import annotations

import os
from pathlib import Path

from .i18n import current_language, t, tf
from .models import (
    HOST_PYTHON,
    UV_PYTHON,
    InterpreterChoice,
    python_version_error,
    resolve_interpreter,
    version_support,
)
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
            f" {t('(default)')}"
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


def _path_has_allowed_extension(path: str, allowed_extensions: tuple[str, ...]) -> bool:
    normalized = path.strip().lower()
    return any(normalized.endswith(ext.lower()) for ext in allowed_extensions)


def _validate_selected_path_extension(
    selected_path: str,
    requested_label: str | None,
    allowed_extensions: tuple[str, ...] | None,
) -> bool:
    if not allowed_extensions:
        return True
    if _path_has_allowed_extension(selected_path, allowed_extensions):
        return True
    expected = ", ".join(allowed_extensions)
    target = requested_label or "file"
    print(
        level_text(
            "WARN",
            tf("The selected path for {} does not match the expected extensions: {}", target, expected),
        )
    )
    return ask_bool("Use this file anyway?", False)


def select_file_path(
    start_dir: str = ".",
    requested_label: str | None = None,
    allowed_extensions: tuple[str, ...] | None = None,
) -> str:
    """A simple, stdlib-only file browser. Returns the chosen path or "" if cancelled."""
    if _last_selected_dir and _last_selected_dir.is_dir():
        current = _last_selected_dir
    else:
        current = Path(start_dir).expanduser().resolve()

    while True:
        if requested_label:
            print(f"\n{title('Select required file')}: {requested_label}")
        print(f"{title('Current directory')}: {current}")
        entries = sorted(current.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
        print(t("  0) Choose a manual path"))
        print(t("  ..) Up one level"))
        print(t("  q) Cancel"))
        for index, entry in enumerate(entries, start=1):
            marker = "/" if entry.is_dir() else ""
            print(f"  {index}) {entry.name}{marker}")

        raw = input(f"{prompt_label('Choose a number, ..,  q, or a manual path')}: ").strip()
        # Both languages' words, since the prompt shows the translated one.
        if raw.lower() in {"q", "cancel", "cancelar", "salir"}:
            return ""
        if raw == "0":
            manual = input(f"{prompt_label('Full file path')}: ").strip()
            if manual:
                resolved = str(Path(manual).expanduser())
                if _validate_selected_path_extension(resolved, requested_label, allowed_extensions):
                    _remember_directory_from_path(resolved)
                    return resolved
            continue
        if raw == "..":
            current = current.parent
            continue
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(entries):
                selected = entries[idx - 1]
                if selected.is_dir():
                    current = selected
                    continue
                selected_text = str(selected)
                if _validate_selected_path_extension(selected_text, requested_label, allowed_extensions):
                    _remember_directory_from_path(selected_text)
                    return selected_text
            continue
        if raw:
            resolved = str(Path(raw).expanduser())
            if _validate_selected_path_extension(resolved, requested_label, allowed_extensions):
                _remember_directory_from_path(resolved)
                return resolved
        print(level_text("ERROR", "Invalid input."))


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


# --- interpreter selection -------------------------------------------------


def choose_interpreter(
    version: str,
    host_python: str | None,
    uv_minors: list[str],
) -> InterpreterChoice | None:
    """Resolve the interpreter for one Odoo version, asking only when the host's
    own ``python3`` cannot be used.

    Returns the choice to build with, or ``None`` when the operator cancels. The
    matrix's recommendation is the default; the operator can keep the host
    interpreter or name any other version, and an out-of-range answer is stated
    plainly (with the evidence tier of the bound being crossed) before it is
    accepted.
    """
    support = version_support(version)
    resolved = resolve_interpreter(version, host_python=host_python)
    if resolved.source != UV_PYTHON:
        return resolved

    recommended = resolved.python or ""
    if host_python and support.python_in_range(host_python):
        # No stated maximum: the host is not outside the range, just unproven.
        warning = tf(
            "Odoo {} states no Python maximum and is not known to build on {}; "
            "Python {} is recommended.",
            version,
            host_python,
            recommended,
        )
    else:
        warning = tf(
            "Odoo {} supports Python {} — this host runs {}.",
            version,
            support.python_range_text(),
            host_python or t("an undetected version"),
        )
    print(level_text("WARN", warning))
    uv_ready = recommended in uv_minors
    if not uv_ready:
        print(
            level_text(
                "INFO",
                tf(
                    "uv cannot provide Python {} on this host — install uv "
                    "(provision check reports it) to build with it.",
                    recommended,
                ),
            )
        )

    keep_host = tf("Keep the host python3 ({})", host_python or "?")
    options = [tf("Build with uv Python {} (recommended)", recommended)] if uv_ready else []
    # Offering the host interpreter when there is none would read as a choice and
    # then cancel.
    # English literals: `choose` shows them translated and returns the original,
    # and it finds its own zero-entry by that literal. Passing a translated
    # "Cancelar" gave the Spanish menu two cancel entries.
    options += ([keep_host] if host_python else []) + [
        "Choose another Python version", "Cancel"
    ]
    answer = choose(tf("Interpreter for Odoo {}", version), options, default_index=None)

    if answer in ("", "Cancel"):
        return None
    if answer == keep_host:
        return _confirmed_choice(version, host_python, host_python, HOST_PYTHON)
    if answer == "Choose another Python version":
        while True:
            chosen = ask_text(t("Python version (e.g. 3.10)"), recommended or None, required=True)
            error = python_version_error(chosen)
            if error is None:
                break
            print(level_text("ERROR", error))
        source = HOST_PYTHON if chosen == host_python else UV_PYTHON
        return _confirmed_choice(version, host_python, chosen, source)
    return resolved


def _confirmed_choice(
    version: str,
    host_python: str | None,
    chosen: str | None,
    source: str,
) -> InterpreterChoice | None:
    """Build the choice for an operator-named interpreter, confirming it first
    when it falls outside the version's declared range."""
    if not chosen:
        return None
    choice = resolve_interpreter(version, host_python=host_python, operator_choice=chosen)
    if not choice.out_of_range:
        return choice
    crossed = choice.crossed
    detail = crossed.describe() if crossed else version_support(version).python_range_text()
    print(
        level_text(
            "WARN",
            tf(
                "Python {} is outside the supported range for Odoo {} (bound: {}).",
                chosen,
                version,
                detail,
            ),
        )
    )
    if not ask_bool(t("Use it anyway?"), False):
        return None
    # Keep the source the operator implied, not the resolver's guess.
    return InterpreterChoice(
        choice.version, choice.python, source, out_of_range=True, crossed=choice.crossed
    )
