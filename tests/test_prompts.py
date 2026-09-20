"""The prompt primitives: what the operator is told, and what their answer means."""

from __future__ import annotations

import pytest

from odoo_dwg import i18n, prompts
from odoo_dwg.models import UV_PYTHON


def _pick_first(monkeypatch):
    monkeypatch.setattr(prompts, "choose", lambda question, options, **kw: options[0])


def test_unproven_host_is_explained_not_called_out_of_range(monkeypatch, capsys):
    _pick_first(monkeypatch)
    choice = prompts.choose_interpreter("12.0", "3.12", ["3.8"])
    assert (choice.python, choice.source) == ("3.8", UV_PYTHON)
    out = capsys.readouterr().out
    assert "states no Python maximum" in out and "3.8 is recommended" in out
    assert "this host runs" not in out


def test_out_of_range_host_still_names_the_range(monkeypatch, capsys):
    _pick_first(monkeypatch)
    choice = prompts.choose_interpreter("14.0", "3.12", ["3.8"])
    assert choice.python == "3.8"
    assert "this host runs 3.12" in capsys.readouterr().out


# --- the cancel contract every menu shares ----------------------------------
#
# `choose` returns one sentinel for "the operator did not choose", and every
# caller compares against it. Making `0` return the first option instead turned
# "Cancel" into "Refresh generated files" on one menu and into the first
# environment to delete on another, with the suite green.


def test_choose_cancels_on_zero_and_on_an_empty_answer_with_no_default(monkeypatch):
    answers = iter(["0", "", "99", "1"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    options = ["Delete everything", "Do nothing"]
    assert prompts.choose("Pick", options) == ""            # 0 cancels
    assert prompts.choose("Pick", options) == ""            # Enter, with no default
    assert prompts.choose("Pick", options) == "Delete everything"  # 99 re-asks, then 1


def test_choose_returns_the_english_option_whatever_the_ui_language(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "1")
    i18n.set_language("es")
    try:
        options = ["Refresh generated files", "Add a version", "Cancel"]
        assert prompts.choose("Pick", options) == "Refresh generated files"
    finally:
        i18n.set_language("en")


@pytest.mark.parametrize("answer,default,expected", [
    ("", False, False),          # Enter takes the default, which is "no" for a plan
    ("", True, True),
    ("y", False, True),
    ("s", False, True),          # the Spanish word, since the prompt may be Spanish
    ("no", True, False),
    ("maybe", False, False),     # an unrecognised answer is never a yes
])
def test_ask_bool_never_turns_a_typo_into_a_yes(monkeypatch, answer, default, expected):
    answers = iter([answer, "", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    assert prompts.ask_bool("Apply this plan now?", default) is expected
