"""The coherence audit: which checks apply, what each reads, and the command's verdict."""

from __future__ import annotations

import pytest

from odoo_dwg import audit, cli
from odoo_dwg.workflows import checks

#: A database shaped like 12.0: statement lines without an entry of their own.
V12 = [["account_journal", "code"], ["account_journal", "default_debit_account_id"],
       ["account_bank_statement_line", "id"], ["account_move_line", "statement_line_id"],
       ["account_move_line", "payment_id"], ["res_company", "period_lock_date"],
       ["ir_model_constraint", "type"], ["ir_model_fields", "required"]]
#: A database shaped like 18.0.
V18 = [["account_journal", "code"], ["account_journal", "suspense_account_id"],
       ["account_bank_statement_line", "id"], ["account_bank_statement_line", "move_id"],
       ["account_bank_statement_line", "is_reconciled"], ["account_move_line", "statement_line_id"],
       ["account_move_line", "payment_id"], ["ir_model_constraint", "type"],
       ["ir_model_fields", "required"]]


def _journal(jid, code, entries=0, company=1):
    return [str(jid), str(company), code, "Journal", "bank", "t", str(entries), ""]


def test_the_checks_follow_the_shape_of_the_database():
    v12, v18 = audit.parse_catalogue(V12), audit.parse_catalogue(V18)
    assert audit.applies("bank-duplicates", v12) and not audit.applies("bank-duplicates", v18)
    assert audit.applies("bank-payments", v12) and audit.applies("bank-closed-lines", v12)
    assert audit.applies("statement-lines-reconciled", v18)
    assert not audit.applies("statement-lines-reconciled", v12)
    for check in ("journal-codes", "constraints-missing", "required-empty"):
        assert audit.applies(check, v12) and audit.applies(check, v18)
    assert not audit.is_odoo(audit.parse_catalogue([["account_journal", "code"]]))


def test_shared_codes_are_a_finding_and_case_only_codes_information():
    shared = audit.journal_codes_result([_journal(1, "BANK1", 5), _journal(2, "BANK1"),
                                         _journal(3, "CSH1"), _journal(4, "csh1")])
    assert shared.verdict == audit.FOUND and shared.count == 1
    assert shared.examples[0] == "company 1: BANK1 (shared, journals 1, 2)"
    assert "differing only by case or spaces: 1" in shared.detail
    case_only = audit.journal_codes_result([_journal(3, "CSH1"), _journal(4, "csh1")])
    assert case_only.verdict == audit.INFO
    other_company = audit.journal_codes_result([_journal(1, "BANK1"), _journal(2, "BANK1", 0, 2)])
    assert other_company.verdict == audit.CLEAN


def test_bank_payments_leave_out_the_duplicates_and_split_by_period():
    rows = [["10", "BANK1", "2025-03-03", "250.00", "f"], ["11", "BANK1", "2020-01-02", "-9.50", "t"],
            ["12", "BANK1", "2025-03-03", "250.00", "f"]]
    result = audit.bank_payments_result(rows, duplicates={12})
    assert result.verdict == audit.FOUND and result.count == 2
    assert result.detail == "closed periods: 1, open periods: 1"
    assert "line 11 (journal BANK1, 2020-01-02, -9.50, closed period)" in result.examples
    assert audit.bank_payments_result([], set()).verdict == audit.CLEAN


def test_closed_period_lines_are_information_only():
    row = ["7", "BANK1", "2020-01-02", "1.00", "", "", "", "", "3", "f"]
    result = audit.bank_closed_lines_result([row], duplicates=set())
    assert result.verdict == audit.INFO and result.count == 1
    assert audit.bank_closed_lines_result([row], duplicates={7}).verdict == audit.CLEAN


def test_a_missing_constraint_is_named_with_its_model_and_definition():
    result = audit.constraints_result([["account.journal", "account_journal_code_company_uniq",
                                        "unique(company_id,code)", "account"]])
    assert result.verdict == audit.FOUND
    assert result.examples == ("account.journal: account_journal_code_company_uniq "
                               "unique(company_id,code) (account)",)


def test_constraint_names_are_compared_as_postgresql_truncates_them():
    assert "left(c.name, 63)" in audit.CONSTRAINTS_MISSING_SQL
    assert "c.type = 'u'" in audit.CONSTRAINTS_MISSING_SQL


def test_required_counts_quote_every_identifier_and_drop_unsafe_ones():
    candidates = audit.parse_candidates([
        ["acme.thing", "partner_id", "acme_thing", "t", "many2one", "t"],
        ["acme.certificate", "file", "acme_certificate", "f", "binary", "f"],
        ["acme.thing", 'x"; DROP TABLE y; --', "acme_thing", "t", "char", "f"],
    ])
    assert [c.field for c in candidates] == ["partner_id", "file"]
    sql = audit.required_counts_sql(candidates)
    assert sql is not None
    assert 'FROM "acme_thing" t WHERE t."partner_id" IS NULL' in sql
    assert 'count(*) FILTER (WHERE t."active")' in sql
    assert ("a.res_model = 'acme.certificate' AND a.res_field = 'file' AND a.res_id = t.id"
            in sql)
    assert audit.required_counts_sql([]) is None


def test_a_field_empty_only_on_archived_records_is_information():
    found = audit.required_result([["acme.thing", "partner_id", "3", "1"],
                                   ["acme.type", "location_id", "5", "0"]])
    assert found.verdict == audit.FOUND and found.count == 1
    assert found.examples == ("acme.thing.partner_id: 3 empty, 1 active",
                              "acme.type.location_id: 5 empty, archived only")
    archived = audit.required_result([["acme.type", "location_id", "5", "0"]])
    assert archived.verdict == audit.INFO
    assert audit.required_result([["acme.thing", "partner_id", "0", "0"]]).verdict == audit.CLEAN


def test_the_audit_selects_the_lines_the_repair_recomputes():
    from odoo_dwg import templates
    assert templates.STALE_RECONCILED_LINES_FROM in audit.STALE_RECONCILED_SQL
    assert templates.STALE_RECONCILED_LINES_FROM in templates._STATEMENT_LINES_REPAIR


def test_examples_are_capped_and_the_rest_counted():
    rows = [[str(i), "BANK1", "2025-01-01"] for i in range(1, 26)]
    result = audit.stale_reconciled_result(rows)
    assert len(result.examples) == audit.EXAMPLES and result.more == 15


@pytest.mark.parametrize("verdicts, expected", [
    ([audit.CLEAN, audit.INFO, audit.NOT_APPLICABLE], 0),
    ([audit.CLEAN, audit.UNREADABLE], 2),
    ([audit.UNREADABLE, audit.FOUND], 1),
])
def test_exit_code(verdicts, expected):
    assert audit.exit_code([audit.Result("x", v) for v in verdicts]) == expected


def _fake_db(catalogue, answers):
    """A psql stand-in: the catalogue, then each query's rows by a fragment it holds.
    None for a query no fragment matches: that check could not be read."""
    def query(sql, *_args):
        if sql == audit.CATALOGUE_SQL:
            return catalogue
        for fragment, rows in answers.items():
            if fragment in sql:
                return rows
        return None
    return query


def test_the_command_on_a_source_copy(monkeypatch, capsys):
    answers = {"j.company_id, j.code": [_journal(1, "BANK1", 5), _journal(2, "BANK1")],
               "twice AS": [], "pay AS": [], "lock AS": [], "ir_model_constraint c": [],
               "f.required AND f.store": []}
    monkeypatch.setattr(checks, "_audit_query", _fake_db(V12, answers))
    assert checks.migration_audit("acme_copy", "127.0.0.1", 5432, "odoo") == checks.FOUND
    out = capsys.readouterr().out
    assert "company 1: BANK1 (shared, journals 1, 2)" in out
    assert "Find journal codes the target refuses" in out
    assert "not applicable to this database" in out  # the reconciled flag, from 14.0
    assert "Nothing was changed" in out


def test_a_migrated_database_with_nothing_to_report(monkeypatch):
    answers = {"j.company_id, j.code": [], "ir_model_constraint c": [],
               "f.required AND f.store": [["acme.thing", "partner_id", "acme_thing", "t",
                                           "many2one", "f"]],
               'FROM "acme_thing"': [["acme.thing", "partner_id", "0", "0"]],
               "l.is_reconciled": []}
    monkeypatch.setattr(checks, "_audit_query", _fake_db(V18, answers))
    assert checks.migration_audit("acme_copy", "127.0.0.1", 5432, "odoo") == checks.CLEAN


def test_one_check_unreadable_leaves_the_others_standing(monkeypatch, capsys):
    answers = {"j.company_id, j.code": [], "f.required AND f.store": [], "l.is_reconciled": []}
    monkeypatch.setattr(checks, "_audit_query", _fake_db(V18, answers))
    assert checks.migration_audit("acme_copy", "127.0.0.1", 5432, "odoo") == checks.UNKNOWN
    out = capsys.readouterr().out
    assert "Declared constraints PostgreSQL does not have: could not be read" in out
    assert "Required fields left empty: none" in out


def test_a_database_that_is_not_odoo_or_cannot_be_read(monkeypatch, capsys):
    monkeypatch.setattr(checks, "_audit_query", lambda *a: None)
    assert checks.migration_audit("acme_copy", "127.0.0.1", 5432, "odoo") == checks.UNKNOWN
    monkeypatch.setattr(checks, "_audit_query", lambda *a: [])
    assert checks.migration_audit("acme_copy", "127.0.0.1", 5432, "odoo") == checks.UNKNOWN
    assert checks.migration_audit('x"; DROP', "127.0.0.1", 5432, "odoo") == checks.UNKNOWN
    out = capsys.readouterr().out
    assert "Cannot read" in out and "not an Odoo database" in out and "Invalid database" in out


def test_the_cli_runs_it_without_asking_anything(monkeypatch):
    seen = {}
    monkeypatch.setattr(checks, "migration_audit",
                        lambda *a: seen.setdefault("args", a) and 0)
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("prompted"))
    cli.main(["migrate", "audit", "--database", "acme_copy", "--db-port", "5433"])
    assert seen["args"] == ("acme_copy", "127.0.0.1", 5433, "odoo")
