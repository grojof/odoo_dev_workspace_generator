"""Unit tests for the i18n layer: English source, Spanish fallback-to-English."""

from __future__ import annotations

import pytest

from odoo_dwg import i18n


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
    assert i18n.tf("Value out of range ({}-{}).", 1, 5) == "Valor fuera de rango (1-5)."


def test_set_language_normalizes_prefix():
    i18n.set_language("es-ES")
    assert i18n.current_language() == "es"
    i18n.set_language("english")
    assert i18n.current_language() == "en"
