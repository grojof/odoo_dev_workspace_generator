"""Unit tests for the i18n layer: English source, Spanish fallback-to-English."""

from __future__ import annotations

import pytest

from odoo_dwg import i18n, ui


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def test_english_is_identity():
    i18n.set_language("en")
    assert i18n.t("Exit") == "Exit"


def test_spanish_translates_known_string():
    i18n.set_language("es")
    assert i18n.t("Exit") == "Salir"


def test_missing_string_falls_back_to_english():
    i18n.set_language("es")
    assert i18n.t("An untranslated string") == "An untranslated string"


def test_tf_translates_template_then_fills():
    i18n.set_language("es")
    # The English template is the catalog key, so interpolation still translates.
    assert i18n.tf("Invalid PostgreSQL role: {}", "x;y") == "Rol PostgreSQL no válido: x;y"


def test_set_language_normalizes_prefix():
    i18n.set_language("es-ES")
    assert i18n.current_language() == "es"
    i18n.set_language("english")
    assert i18n.current_language() == "en"


# --- every operator-facing string has a Spanish entry ------------------------

import ast  # noqa: E402
from pathlib import Path  # noqa: E402

PACKAGE = Path(__file__).resolve().parent.parent / "odoo_dwg"
# Calls whose first argument is shown to the operator (translated at a chokepoint).
_FIRST_ARG = {
    "t", "tf", "ask_text", "ask_bool",
    "prompt_label", "title", "confirm_with_phrase", "choose", "Command",
}


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else None


def _ui_literals() -> dict[str, str]:
    """Every string literal the UI translates, mapped to where it appears."""
    found: dict[str, str] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.name == "i18n.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node.func)
            candidates: list[ast.expr] = []
            if name in _FIRST_ARG and node.args:
                candidates.append(node.args[0])
            if name == "level_text" and len(node.args) > 1:
                candidates.append(node.args[1])
            if name in ("choose", "render_table"):
                listed = node.args[1] if name == "choose" and len(node.args) > 1 else (
                    node.args[0] if name == "render_table" and node.args else None
                )
                if isinstance(listed, ast.BinOp):
                    listed = listed.left
                if isinstance(listed, ast.List):
                    candidates += listed.elts
            for candidate in candidates:
                if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
                    if candidate.value.strip():
                        found.setdefault(candidate.value, f"{path.name}:{candidate.lineno}")
    return found


def test_every_ui_string_has_a_spanish_translation():
    literals = _ui_literals()
    assert len(literals) > 150  # the extractor still sees the UI
    missing = {text: where for text, where in literals.items() if text not in i18n._ES}
    assert not missing, f"add these to i18n._ES: {missing}"


def test_the_catalog_is_authored_in_the_direction_it_is_read():
    """English keys, Spanish values — the same direction `t()` looks up.

    The catalog used to be written Spanish→English and inverted at import, which
    silently merged any two English strings whose Spanish happened to match."""
    for english, spanish in i18n._ES.items():
        assert isinstance(english, str) and isinstance(spanish, str)
    # No key appears twice (Python would have merged them), and the values are
    # free to repeat — two English strings may legitimately share one Spanish.
    assert len(i18n._ES) > 250
    # A key is the literal the code passes to t()/tf(), so it must be English:
    # nothing that is only in the Spanish half may be a key.
    spanish_only = {"í", "ó", "¿", "¡", "ñ"}
    # "Español" is the language's own name: the same word on both sides.
    suspicious = [k for k in i18n._ES
                  if k != "Español" and any(ch in k for ch in spanish_only)]
    assert not suspicious, f"these keys look Spanish: {suspicious}"


def test_a_table_cell_carries_colour_and_nothing_else():
    """Module names and authors come from the database under migration, and land
    in the preflight table: a cell must not be able to drive the terminal."""
    cell = "evil\x1b[2J\x1b[1;31mFAKE OK\x1b[0m\x1b]0;title\x07\rmore\tand\x1b"
    out = ui.render_table(["State", "Module"], [["MISSING", cell]])
    for control in ("\x1b[2J", "\x1b]0;", "\r", "\t"):
        assert control not in out, control
    assert "\x1b[1;31m" in out and "\x1b[0m" in out       # colour survives
    assert out.count("\n") == 5                            # and the borders hold

    # Colour a cell opens and never closes would run past the border: `\x1b[8m`
    # (conceal) from a module name hides every row printed after it.
    opened = ui.render_table(["State", "Module"], [["MISSING", "sale\x1b[8m"], ["OK", "stock"]])
    assert opened.rstrip().endswith("+")                  # the table ends in a border
    assert "stock" in ui.strip_ansi(opened)
    for row in opened.splitlines():
        assert row.count("\x1b[") == 0 or row.endswith("|"), row
    assert ui.sanitize_cell("sale\x1b[8m").endswith("\x1b[0m")
