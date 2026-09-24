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
    monkeypatch.setattr(wi, "psql_rows", lambda sql, *a, **k:
                        [["10", "9", "500", "120", "7"]] if sql == it.BANK_LINES_STATS_SQL else ROWS)
    wi.find_bank_duplicates(env)
    joined = "\n".join(c.command for c in plans[0])
    assert "bank-duplicate-lines.tsv" in joined and "bank-duplicate-lines.sql" in joined
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
