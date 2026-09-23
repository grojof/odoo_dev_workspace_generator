"""The findings ledger from outside: the read-only commands and the menu's plans."""

from __future__ import annotations

import json

import pytest

from odoo_dwg import cli
from odoo_dwg import findings as fl
from odoo_dwg.models import MigrationEnv
from odoo_dwg.workflows import findings as wf
from tests.test_findings import TABLES, _raw

CHAIN = ["--source", "12.0", "--target", "18.0", "--lang", "en"]


@pytest.fixture
def env(tmp_path, monkeypatch) -> MigrationEnv:
    monkeypatch.setattr(MigrationEnv, "base_dir", str(tmp_path))
    return MigrationEnv(source="12.0", target="18.0")


def _write(env: MigrationEnv, raw: dict | None = None) -> None:
    env.findings_data_dir.mkdir(parents=True)
    env.findings_ledger.write_text(json.dumps(raw or _raw()), encoding="utf-8")
    rows = TABLES["sii.tsv"]
    (env.findings_data_dir / "sii.tsv").write_text(
        "\n".join("\t".join(r) for r in rows) + "\n", encoding="utf-8")


def _run(*args: str) -> int:
    return cli.main(["migrate", "findings", *args, *CHAIN])


def test_no_ledger_yet_is_said_and_nothing_fails(env, capsys):
    assert _run("list") == 0
    assert "No findings ledger yet" in capsys.readouterr().out
    assert not env.findings_dir.exists()  # a read-only command wrote nothing


def test_pending_decisions_make_the_list_exit_non_zero(env, capsys):
    _write(env)
    assert _run("list") == 1
    out = capsys.readouterr().out
    assert "sii-pending" in out and "await a decision" in out
    raw = _raw()
    for finding in raw["findings"]:
        finding["decision"]["state"] = "accepted"
    env.findings_ledger.write_text(json.dumps(raw), encoding="utf-8")
    assert _run("list") == 0


def test_an_invalid_ledger_is_named_problem_by_problem(env, capsys):
    raw = _raw()
    raw["findings"][0]["query"] = ""
    _write(env, raw)
    assert _run("validate") == 1
    assert "sii-pending.query: required" in capsys.readouterr().out
    assert _run("list") == 2  # could not tell: not a clean result


def test_show_prints_one_finding_in_full(env, capsys):
    _write(env)
    assert _run("show", "sii-pending") == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["query"].startswith("select sii_state")
    assert _run("show", "nope") == 2


def test_a_report_is_printed_in_its_own_language(env, capsys):
    _write(env)
    assert _run("report", "--report-lang", "es") == 0
    out = capsys.readouterr().out
    assert "Lo que hemos encontrado" in out and "SII activo en modo real" in out
    assert not env.reports_dir.exists()  # printed, not written


def test_a_report_that_cannot_be_rendered_says_why(env, capsys):
    raw = _raw()
    del raw["findings"][0]["client"]["es"]
    _write(env, raw)
    assert _run("report", "--report-lang", "es") == 2
    assert "no es client text" in capsys.readouterr().out


def test_links_are_checked_without_the_network(env, capsys, monkeypatch):
    _write(env)
    monkeypatch.setattr(wf, "url_status", lambda url: (404, "Not Found"))
    assert _run("links") == 1
    assert "context.versions[0].link" in capsys.readouterr().out
    monkeypatch.setattr(wf, "url_status", lambda url: (200, ""))
    assert _run("links") == 0


def test_a_private_source_is_not_a_broken_link():
    ledger = fl.parse_ledger(json.dumps(_raw()))
    asked: list[str] = []
    wf.broken_links(ledger, lambda url: (asked.append(url), (200, ""))[1])
    assert asked == ["https://github.com/odoo/odoo/tree/18.0"]


# --- the menu builds plans, and writes only what the operator confirmed --------------

def _answers(monkeypatch, *answers: str) -> None:
    queue = list(answers)
    monkeypatch.setattr(wf, "choose", lambda *a, **k: queue.pop(0))
    monkeypatch.setattr(wf, "ask_text", lambda *a, **k: queue.pop(0))


def _captured(monkeypatch) -> list:
    plans: list = []
    monkeypatch.setattr(wf, "apply_if_confirmed", lambda commands: (plans.append(commands), False)[1])
    return plans


def _heredoc_body(command: str) -> str:
    """What a ``write_text_file_command`` writes: the lines between its header
    (``cat > … <<'END'``) and the line holding only the delimiter."""
    header, rest = command.split("\n", 1)
    delimiter = header.rsplit("<<'", 1)[1].rstrip("'")
    lines = rest.split("\n")
    return "\n".join(lines[: lines.index(delimiter)]) + "\n"


def test_writing_the_reports_plans_both_files_in_the_chosen_language(env, monkeypatch):
    _write(env)
    _answers(monkeypatch, "es")
    plans = _captured(monkeypatch)
    wf._write_reports(env)
    text = "\n".join(c.command for c in plans[0])
    assert "findings-client.es.md" in text and "findings-extended.es.md" in text
    assert "Lo que hemos encontrado" in text


def test_a_decision_rewrites_the_ledger_with_the_history(env, monkeypatch):
    _write(env)
    _answers(monkeypatch, "sii-pending", "act", "client, meeting of 24/09")
    plans = _captured(monkeypatch)
    wf._decide(env)
    written = next(c.command for c in plans[0] if "findings.json" in c.command)
    finding = fl.parse_ledger(_heredoc_body(written)).findings[0]
    assert finding.decision.state == "act" and finding.decision.note == "client, meeting of 24/09"
    assert finding.history[0].state == "pending"
    assert json.loads(env.findings_ledger.read_text())["findings"][0]["decision"]["state"] == \
        "pending"  # nothing written: the operator did not confirm


def test_a_refused_change_writes_nothing(env, monkeypatch, capsys):
    _write(env)
    _answers(monkeypatch, "sii-pending", "  ")  # a withdrawal with no reason
    plans = _captured(monkeypatch)
    wf._withdraw(env)
    assert plans == []
    assert "reason" in capsys.readouterr().out
