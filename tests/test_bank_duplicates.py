"""Bank statement lines imported twice: the guarded SQL and the intake step."""

from __future__ import annotations

import pytest

from odoo_dwg import intake as it
from odoo_dwg.models import MigrationEnv
from odoo_dwg.workflows import intake as wi

ROWS = [["duplicate", "11", "2", "BNK1", "2025-03-03", "-1.50", "5"],
        ["duplicate", "12", "2", "BNK1", "2025-03-03", "-1.50", "6"],
        ["reconciled twice", "13", "2", "BNK1", "2025-03-03", "-12.30", "7"]]


def test_copies_are_parsed_and_short_rows_skipped():
    copies = it.parse_bank_copies([*ROWS, ["duplicate", "1"]])
    assert [c.line for c in copies] == [11, 12, 13] and copies[0].kept == 5


def test_the_sql_deletes_only_duplicates_and_guards_each_line():
    sql = it.bank_duplicates_sql(it.parse_bank_copies(ROWS))
    assert "(11, 5)" in sql and "(12, 6)" in sql and "(13, 7)" not in sql
    assert "NOT EXISTS (SELECT 1 FROM account_move_line m WHERE m.statement_line_id = d.id)" in sql
    assert "IS NOT DISTINCT FROM" in sql and "2 unreconciled copies" in sql


def test_no_duplicate_writes_a_harmless_file():
    assert it.bank_duplicates_sql([]).startswith("--") and "DELETE" not in it.bank_duplicates_sql([])


def test_the_query_is_one_select_with_no_temporary_table():
    for sql in (it.BANK_DUPLICATES_SQL, it.BANK_LINES_STATS_SQL):
        assert sql.lstrip().startswith("WITH") and "TEMP" not in sql.upper().replace("TEMPORARY", "")
        assert ";" not in sql


@pytest.fixture
def env(tmp_path, monkeypatch) -> MigrationEnv:
    monkeypatch.setattr(MigrationEnv, "base_dir", str(tmp_path))
    env = MigrationEnv(source="12.0", target="18.0")
    env.intake = it.IntakeRecord("ACME_original", archive_root="client-src/acme")
    return env


def test_the_step_records_the_table_the_sql_and_a_finding(env, monkeypatch):
    plans = []
    monkeypatch.setattr(wi, "apply_if_confirmed", lambda commands: plans.append(commands) or False)
    monkeypatch.setattr(wi, "ask_text", lambda *a, **k: "ACME")
    answers = {it.BANK_LINES_STATS_SQL: [["10", "9", "500", "120", "7"]], it.BANK_LOCKED_SQL: LOCKED}
    monkeypatch.setattr(wi, "psql_rows", lambda sql, *a, **k: answers.get(sql, ROWS))
    wi.find_bank_duplicates(env)
    joined = "\n".join(c.command for c in plans[0])
    assert "bank-duplicate-lines.tsv" in joined and "bank-duplicate-lines.sql" in joined
    assert "bank-locked-unreconciled.tsv" in joined and "bank-locked-unreconciled.sql" in joined
    assert '"closed_period_kept": 1' in joined and '"closed_period_to_leave": 1' in joined
    assert "(11, 5)" in joined and "13.0-pre.sql" in joined
    assert '"duplicates": 2' in joined and '"reconciled_twice"' in joined


def test_a_source_from_14_is_refused(env, monkeypatch, capsys):
    env.source, env.target = "14.0", "18.0"
    monkeypatch.setattr(wi, "psql_rows", lambda *a, **k: pytest.fail("read"))
    wi.find_bank_duplicates(env)
    assert "up to 13.0" in capsys.readouterr().out


def test_an_unreadable_reference_records_nothing(env, monkeypatch, capsys):
    monkeypatch.setattr(wi, "psql_rows", lambda *a, **k: None)
    monkeypatch.setattr(wi, "apply_if_confirmed", lambda c: pytest.fail("recorded"))
    wi.find_bank_duplicates(env)
    assert "nothing recorded" in capsys.readouterr().out


#: line, journal, date, amount, label, ref, partner, note, statement, kept
LOCKED = [["11", "BNK1", "2025-03-03", "-1.50", "fee", "", "", "", "2", "f"],   # a duplicate
          ["21", "BNK1", "2025-03-01", "10", "transfer", "", "ACME", "", "1", "f"],
          ["22", "BNK1", "2025-03-02", "50", "payment", "R1", "ACME", "", "1", "t"]]


def test_closed_period_lines_leave_out_duplicates_and_mark_what_is_kept():
    lines = it.parse_locked_lines(LOCKED, {11})
    assert [(x.line, x.kept) for x in lines] == [(21, False), (22, True)]


def test_the_optional_sql_leaves_behind_only_unmatched_lines_still_in_a_closed_period():
    sql = it.locked_lines_sql(it.parse_locked_lines(LOCKED, {11}))
    assert "OPTIONAL" in sql and "21" in sql.split("WHERE d.id IN (")[1].split(")")[0]
    assert "22" not in sql.split("WHERE d.id IN (")[1].split(")")[0]
    assert "greatest(c.fiscalyear_lock_date, c.period_lock_date)" in sql
    assert "NOT EXISTS (SELECT 1 FROM account_move_line m" in sql


def test_no_closed_period_line_writes_a_harmless_file():
    assert "DELETE" not in it.locked_lines_sql([])


def test_text_columns_are_flattened_in_the_query():
    assert r"'[\t\n\r]+'" in it.BANK_LOCKED_SQL and "\t" not in it.BANK_LOCKED_SQL
