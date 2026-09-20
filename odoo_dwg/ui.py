"""Terminal styling and table rendering (mirrors ``odoo_instance_manager``).

Standard-library only. All user-facing strings pass through the i18n layer so
the whole UI honours the selected language, and colour degrades to plain text
when the stream is not a TTY (or ``NO_COLOR`` is set).
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import textwrap

from .i18n import t

_RESET = "\033[0m"
_STYLES = {
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
}


def supports_color() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("FORCE_COLOR") is not None:
        return True

    stream = sys.stdout
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False

    term = os.environ.get("TERM", "").lower()
    if term in {"", "dumb"}:
        return False

    return True


def style(text: str, *tokens: str) -> str:
    if not supports_color() or not tokens:
        return text

    prefix = "".join(_STYLES[token] for token in tokens if token in _STYLES)
    if not prefix:
        return text
    return f"{prefix}{text}{_RESET}"


def level_text(level: str, message: str) -> str:
    message = t(message)
    token_map = {
        "INFO": ("blue",),
        "WARN": ("yellow", "bold"),
        "ERROR": ("red", "bold"),
        "OK": ("green", "bold"),
        "MISSING": ("yellow", "bold"),
    }
    tokens = token_map.get(level, ())
    label = style(f"[{level}]", *tokens)
    return f"{label} {message}" if label else f"[{level}] {message}"


def level_tag(level: str) -> str:
    return level_text(level, "").rstrip()


def prompt_label(label: str) -> str:
    return style(t(label), "cyan")


def title(text: str) -> str:
    return style(t(text), "bold")


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Terminal control that is not colour. A table cell can carry text this tool did
# not write — a module name or author read from a restored database, `pg_restore`
# on its stderr — and `\x1b[2J` clears the screen, an OSC sequence retitles the
# window, a lone `\r` overwrites the line. Colour (SGR, the sequences ending in
# `m`) is what this tool itself emits, so it is first and is the only group:
# whatever it matches is kept and everything after it is dropped — including a
# bare ESC, which the last class catches once the sequences have had their turn.
_TERMINAL_CONTROL_RE = re.compile(
    r"(\x1b\[[0-9;]*m)"                    # SGR — this tool's own colour
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC …BEL / …ST
    r"|\x1b\[[0-9;?]*[A-Za-z]"             # any other CSI
    r"|\x1b[@-Z\\-_]"                      # two-character escapes
    r"|[\x00-\x08\x0b-\x0d\x0e-\x1f\x7f]"  # C0 controls, keeping \t and \n
)


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def sanitize_cell(text: str) -> str:
    """Text safe to print inside a table: colour, but no other terminal control.

    A newline is left alone — the table renders a cell over several lines and the
    borders still hold — but a tab would shift the columns it lands in.
    """
    kept = _TERMINAL_CONTROL_RE.sub(lambda match: match.group(1) or "", text)
    # Colour that a cell opened and never closed would run past the border into
    # the rest of the table — `\x1b[8m` (conceal) from a module name read out of
    # a restored database hides everything printed after it.
    if "\x1b[" in kept:
        kept += _RESET
    return kept.replace("\t", " ")


def _visible_len(text: str) -> int:
    return len(_ANSI_RE.sub("", text))


_MIN_COL = 10


def _fit_caps(natural: list[int], available: int) -> list[int]:
    """Shrink the widest column one char at a time until the row fits `available`."""
    caps = list(natural)
    while sum(caps) > available and max(caps) > _MIN_COL:
        widest = caps.index(max(caps))
        caps[widest] -= 1
    return caps


_SGR_LEAD_RE = re.compile(r"^(?:\x1b\[[0-9;]*m)+")


def _leading_sgr(text: str) -> str:
    match = _SGR_LEAD_RE.match(text)
    return match.group(0) if match else ""


def wrap_plain_block(text: str, width: int) -> list[str]:
    """Wrap every line of `text` (which may contain newlines) to `width`."""
    width = max(1, width)
    out: list[str] = []
    for line in text.splitlines() or [""]:
        out.extend(
            textwrap.wrap(line, width=width, break_long_words=True, break_on_hyphens=False)
            or [""]
        )
    return out


def _wrap_cell(cell: str, cap: int) -> list[str]:
    """Split a cell into display lines, wrapping lines longer than `cap`.

    Wrapping is done on the *visible* text; a leading SGR style (from `style()`)
    and a trailing reset are re-applied to each wrapped piece so escape sequences
    are never split mid-code and short styled tags render unchanged.
    """
    lines: list[str] = []
    for line in cell.splitlines() or [""]:
        if _visible_len(line) <= cap:
            lines.append(line)
            continue
        lead = _leading_sgr(line)
        trail = _RESET if line.endswith(_RESET) else ""
        for chunk in wrap_plain_block(strip_ansi(line), cap):
            lines.append(f"{lead}{chunk}{trail}")
    return lines or [""]


def render_table(
    headers: list[str], rows: list[list[str]], max_width: int | None = None
) -> str:
    safe_headers = [sanitize_cell(t(str(item))) for item in headers]
    safe_rows = [[sanitize_cell(t(str(cell))) for cell in row] for row in rows]
    column_count = len(safe_headers)
    if column_count == 0:
        return ""

    normalized_rows = []
    for row in safe_rows:
        if len(row) < column_count:
            normalized_rows.append(row + [""] * (column_count - len(row)))
        else:
            normalized_rows.append(row[:column_count])

    # Natural (unwrapped) width each column would like.
    natural = [_visible_len(head) for head in safe_headers]
    for row in normalized_rows:
        for index, cell in enumerate(row):
            for line in cell.splitlines() or [""]:
                natural[index] = max(natural[index], _visible_len(line))

    # Cap columns so the whole table fits the terminal width, then wrap to the caps.
    if max_width is None:
        max_width = shutil.get_terminal_size((100, 24)).columns
    overhead = 3 * column_count + 1
    available = max(max_width - overhead, column_count * _MIN_COL)
    caps = _fit_caps(natural, available)

    wrapped_header = [_wrap_cell(head, caps[i]) for i, head in enumerate(safe_headers)]
    wrapped_rows = [
        [_wrap_cell(cell, caps[i]) for i, cell in enumerate(row)]
        for row in normalized_rows
    ]

    # Actual widths from the wrapped content (each <= its cap).
    widths = []
    for i in range(column_count):
        candidates = [_visible_len(line) for line in wrapped_header[i]]
        for row in wrapped_rows:
            candidates.extend(_visible_len(line) for line in row[i])
        widths.append(max(candidates) if candidates else 1)

    def _pad(cell: str, width: int) -> str:
        extra = width - _visible_len(cell)
        return cell + (" " * max(0, extra))

    def _render_row(cells: list[list[str]]) -> list[str]:
        row_height = max((len(parts) for parts in cells), default=1)
        out: list[str] = []
        for line_idx in range(row_height):
            rendered = [
                _pad(parts[line_idx] if line_idx < len(parts) else "", widths[col_idx])
                for col_idx, parts in enumerate(cells)
            ]
            out.append("| " + " | ".join(rendered) + " |")
        return out

    horizontal = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    lines = [horizontal]
    lines.extend(_render_row(wrapped_header))
    lines.append(horizontal)
    for row in wrapped_rows:
        lines.extend(_render_row(row))
    lines.append(horizontal)
    return "\n".join(lines)
