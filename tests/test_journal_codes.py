"""Journal codes the target refuses: shared or confusable codes, renamed before the chain."""

from __future__ import annotations

import pytest

from odoo_dwg import intake as it
from odoo_dwg.models import MigrationEnv
from odoo_dwg.workflows import intake as wi

#: id, company, code, name, type, active, entries, last entry
ROWS = [["101", "1", "BANK1", "Bank A", "bank", "t", "900", "2025-01-01"],
        ["102", "1", "BANK1", "Bank B", "bank", "t", "40", "2024-01-01"],
        ["103", "1", "BANK2", "Card", "bank", "t", "0", ""],
        ["104", "1", "CASH", "Account A", "bank", "t", "60", "2022-01-01"],
        ["105", "1", "CASH ", "Account B", "bank", "t", "7", "2022-01-01"],
        ["106", "2", "BANK1", "Other company", "bank", "t", "5", "2024-01-01"]]


def _by_id(plan):
    return {j.id: j for j in plan}


def test_the_journal_with_most_entries_keeps_the_shared_code():
    plan, problems = it.journal_code_plan(ROWS)
    by = _by_id(plan)
    assert not problems
    assert by[101].proposed == "" and by[102].proposed and by[102].group == "shared"
    assert 106 not in by  # another company's BANK1 is not a clash
    assert 103 not in by


def test_codes_that_differ_only_by_a_space_are_confusable():
    by = _by_id(it.journal_code_plan(ROWS)[0])
    assert by[104].proposed == "" and by[105].group == "confusable" and by[105].proposed


def test_proposals_are_short_and_unique_in_the_company():
    plan, _ = it.journal_code_plan(ROWS)
    proposed = {j.id: j.proposed for j in plan if j.proposed}
    codes = [proposed.get(int(r[0]), r[2].strip()) for r in ROWS if r[1] == "1"]
    assert all(len(c) <= 5 for c in codes)
    assert len({c.upper() for c in codes}) == len(codes)
    assert _by_id(plan)[102].proposed not in ("BANK1", "BANK2", "CASH")


def test_the_operators_code_is_kept_and_a_bad_one_refused():
    plan, problems = it.journal_code_plan(ROWS, {102: "ACME1"})
    assert _by_id(plan)[102].proposed == "ACME1" and not problems
    _, problems = it.journal_code_plan(ROWS, {102: "AC ME"})
    assert "not 1 to 5 letters or digits" in problems[0]
    _, problems = it.journal_code_plan(ROWS, {102: "BANK2"})
    assert "also journal 103" in problems[0]


def test_the_sql_renames_only_while_the_old_code_holds_and_the_new_is_free():
    plan, _ = it.journal_code_plan(ROWS, {102: "ACME1"})
    sql = it.journal_codes_sql(plan)
    assert "SET code = 'ACME1' WHERE id = 102 AND code = 'BANK1'" in sql
    assert "o.company_id = 1 AND o.code = 'ACME1'" in sql
    assert "WHERE id = 101" not in sql and "WHERE id = 105 AND code = 'CASH '" in sql
    assert "DELETE" not in sql and "ir_sequence" not in sql


def test_nothing_to_rename_writes_a_harmless_file():
    assert "UPDATE" not in it.journal_codes_sql([])


@pytest.fixture
def env(tmp_path, monkeypatch) -> MigrationEnv:
    monkeypatch.setattr(MigrationEnv, "base_dir", str(tmp_path))
    env = MigrationEnv(source="12.0", target="18.0")
    env.intake = it.IntakeRecord("ACME_original", archive_root="client-src/acme")
    return env


def _run(env, monkeypatch):
    plans = []
    monkeypatch.setattr(wi, "apply_if_confirmed", lambda commands: plans.append(commands) or False)
    monkeypatch.setattr(wi, "ask_text", lambda *a, **k: "ACME")
    monkeypatch.setattr(wi, "psql_rows", lambda *a, **k: ROWS)
    wi.find_journal_codes(env)
    return "\n".join(c.command for c in plans[0]) if plans else ""


def test_the_step_writes_the_table_the_sql_and_a_finding(env, monkeypatch):
    joined = _run(env, monkeypatch)
    assert "journal-codes.tsv" in joined and "journal-codes.sql" in joined
    assert '"id": "journal-codes-1"' in joined and "13.0-pre.sql" in joined


def test_the_step_keeps_the_codes_the_operator_wrote_in_the_table(env, monkeypatch):
    table = env.findings_data_dir / "journal-codes.tsv"
    table.parent.mkdir(parents=True)
    table.write_text("company\tjournal_id\tname\ttype\tactive\tentries\tlast_entry\tgroup\tcode\tproposed\n"
                     "1\t102\tBank B\tbank\tyes\t40\t2024-01-01\tshared\tBANK1\tACME1\n")
    assert "SET code = 'ACME1' WHERE id = 102" in _run(env, monkeypatch)


def test_a_bad_code_in_the_table_stops_the_step(env, monkeypatch, capsys):
    table = env.findings_data_dir / "journal-codes.tsv"
    table.parent.mkdir(parents=True)
    table.write_text("c\tj\tn\tt\ta\te\tl\tg\tcode\tproposed\n"
                     "1\t102\tB\tbank\tyes\t40\t\tshared\tBANK1\tAC-ME\n")
    assert _run(env, monkeypatch) == ""
    assert "AC-ME" in capsys.readouterr().out
