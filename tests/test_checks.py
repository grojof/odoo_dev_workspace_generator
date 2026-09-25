"""The read-only surface: what it finds, and what it says by exiting."""

from __future__ import annotations

import json

import pytest

from odoo_dwg import cli, egress
from odoo_dwg.workflows import checks


def _present(rules: list[dict]) -> dict[str, str]:
    return {egress.rule_filename(rule): egress.render_rule(rule) for rule in rules}


def test_rules_as_the_tool_left_them_report_nothing():
    rules = egress.baseline_rules(["192.168.1.1"])
    assert egress.audit_rules(_present(rules), rules) == []


def test_a_rule_that_sorts_ahead_is_the_finding_that_leads():
    rules = egress.baseline_rules([])
    present = _present(rules)
    # `-` sorts before a digit, which is the whole reason the prefix is `00-odwg-`.
    present["00-aaa-allow.json"] = json.dumps({"name": "aaa", "action": "allow"})
    present["000-allow-everything.json"] = json.dumps({"name": "zzz", "action": "allow"})
    findings = egress.audit_rules(present, rules)
    assert [(f.kind, f.filename) for f in findings] == [("sorts first", "00-aaa-allow.json")]


def test_an_owned_rule_that_is_gone_changed_or_switched_off():
    rules = egress.baseline_rules([])
    present = _present(rules)
    gone = egress.rule_filename(rules[0])
    edited = egress.rule_filename(rules[1])
    off = egress.rule_filename(rules[2])
    del present[gone]
    present[edited] = json.dumps({**rules[1], "action": "allow-everything"})
    present[off] = json.dumps({**rules[2], "enabled": False})
    found = {(f.kind, f.filename) for f in egress.audit_rules(present, rules)}
    assert ("absent", gone) in found
    assert ("changed", edited) in found
    assert ("disabled", off) in found


def test_formatting_alone_is_not_reported_as_a_change():
    # Compared as data: a rule re-indented by hand does nothing different, and
    # reporting it would train the reader to ignore this check.
    rules = egress.baseline_rules([])
    present = _present(rules)
    present[egress.rule_filename(rules[0])] = json.dumps(rules[0], indent=8, sort_keys=True)
    assert egress.audit_rules(present, rules) == []


def test_a_rule_directory_that_cannot_be_read_is_not_a_clean_result(monkeypatch, capsys):
    monkeypatch.setattr(checks, "read_dir_files", lambda *a, **k: None)
    assert checks.egress_check() == checks.UNKNOWN
    assert "Cannot read" in capsys.readouterr().out


def test_clean_rules_exit_zero_and_findings_exit_one(monkeypatch, capsys):
    rules = egress.baseline_rules([])
    monkeypatch.setattr(checks, "read_text", lambda *a, **k: "")
    monkeypatch.setattr(checks, "read_dir_files", lambda *a, **k: _present(rules))
    assert checks.egress_check() == checks.CLEAN
    present = _present(rules)
    present["00-aaa.json"] = json.dumps({"name": "a"})
    monkeypatch.setattr(checks, "read_dir_files", lambda *a, **k: present)
    assert checks.egress_check() == checks.FOUND
    # It names the action and performs none: nothing here writes.
    assert "Nothing was changed" in capsys.readouterr().out


def test_the_checks_refuse_a_name_postgresql_would_not_take(capsys):
    assert checks.mail_check('db"; DROP DATABASE x --', "127.0.0.1", 5432, "odoo") == checks.UNKNOWN
    assert checks.probe_check("12.0", "19.0", "acme copy") == checks.UNKNOWN
    assert "Invalid database name" in capsys.readouterr().out


@pytest.mark.parametrize(
    "state,expected",
    [
        (egress.MailState(servers=(), captured=True), checks.CLEAN),
        (
            egress.MailState(
                servers=(egress.MailServer("1", "Client", "smtp.example", "587", True),)
            ),
            checks.FOUND,
        ),
        (egress.MailState(servers=(), fetchmail_active=1, captured=True), checks.FOUND),
    ],
)
def test_mail_check_exits_on_whether_mail_can_leave(monkeypatch, state, expected):
    monkeypatch.setattr(checks, "mail_state", lambda *a, **k: state)
    assert checks.mail_check("acme_copy", "127.0.0.1", 5432, "odoo") == expected


def test_a_database_that_cannot_be_read_is_not_a_clean_result(monkeypatch):
    monkeypatch.setattr(checks, "mail_state", lambda *a, **k: None)
    assert checks.mail_check("acme_copy", "127.0.0.1", 5432, "odoo") == checks.UNKNOWN


def test_mail_without_its_action_is_a_usage_error_not_a_traceback(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["mail"])
    assert exit_info.value.code == 2
    assert "the only action is 'check'" in capsys.readouterr().err
