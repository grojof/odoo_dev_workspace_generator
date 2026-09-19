"""Interpreter prompt: what the operator is told, with the answer stubbed."""

from __future__ import annotations

from odoo_dwg import prompts
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
