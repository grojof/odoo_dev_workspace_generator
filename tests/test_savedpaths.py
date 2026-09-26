"""Saved filters and exports whose fields the chain renamed: rewritten at the target step."""

from __future__ import annotations

import ast
import json

from odoo_dwg import savedpaths, templates
from odoo_dwg.models import MigrationEnv

#: A target shaped like 18.0, only the fields the tests follow.
FIELDS = {
    "account.move": {"name": "", "invoice_date": "", "invoice_origin": "", "ref": "",
                     "payment_reference": "", "partner_id": "res.partner", "move_type": "",
                     "date": ""},
    "account.move.line": {"move_id": "account.move", "account_id": "account.account",
                          "reconciled": "", "date_maturity": "",
                          "distribution_analytic_account_ids": "account.analytic.account"},
    "account.account": {"account_type": "", "name": ""},
    "account.analytic.account": {"name": ""},
    "account.journal": {"default_account_id": "account.account"},
    "res.partner": {"name": "", "customer_rank": "", "supplier_rank": "",
                    "company_id": "res.company"},
    "res.company": {"tax_agency_id": "aeat.tax.agency"},
    "aeat.tax.agency": {"name": ""},
    "sale.order": {"invoice_ids": "account.move", "name": ""},
    "stock.picking": {"move_ids": "stock.move"},
    "stock.move": {"quantity": ""},
    "product.template": {"list_price": "", "name": ""},
}


def test_it_applies_to_a_source_up_to_12():
    assert savedpaths.applies(12, 13) and savedpaths.applies(11, 18)
    assert not savedpaths.applies(13, 18) and not savedpaths.applies(12, 12)


def test_a_path_follows_the_targets_relations_and_renames_each_segment():
    path = savedpaths.rewrite_path
    assert path(FIELDS, "sale.order", "invoice_ids/date_invoice", "/") == "invoice_ids/invoice_date"
    assert path(FIELDS, "stock.picking", "move_lines/quantity_done", "/") == "move_ids/quantity"
    assert path(FIELDS, "res.partner", "company_id/sii_tax_agency_id/display_name", "/") == \
        "company_id/tax_agency_id/display_name"
    # A successor that is not relational ends the path.
    assert path(FIELDS, "account.account", "user_type_id/.id", "/") == "account_type"
    # A grouping suffix and a sort sign are kept; what the target does not know is kept too.
    assert path(FIELDS, "account.move", "date_invoice:month", ".") == "invoice_date:month"
    assert path(FIELDS, "sale.order", "x_custom/date_invoice", "/") == "x_custom/date_invoice"
    # No successor.
    assert path(FIELDS, "res.partner", "contracts_count", "/") is None


def test_a_successor_is_used_only_when_the_target_has_it_and_lacks_the_old_name():
    target = {"account.move": {"number": "", "name": ""}}
    assert savedpaths.rewrite_path(target, "account.move", "number", "/") == "number"
    assert savedpaths.rewrite_path({"account.move": {}}, "account.move", "date_invoice", "/") \
        == "date_invoice"


def _domain(result: savedpaths.FilterResult) -> list:
    return ast.literal_eval(result.domain)


def test_a_domain_value_follows_its_field_even_inside_a_path():
    result = savedpaths.rewrite_filter(
        FIELDS, "account.move.line",
        '["&", ("account_id.internal_type", "=", "payable"), ("reconciled", "=", False)]',
        "{}", "[]")
    assert _domain(result) == ["&", ("account_id.account_type", "=", "liability_payable"),
                               ("reconciled", "=", False)]
    left = savedpaths.rewrite_filter(
        FIELDS, "account.move.line", '[("account_id.internal_type", "=", "other")]', "{}", "[]")
    assert not left.changed and "internal_type" in left.stuck


def test_conditions_replace_fields_no_single_field_replaces():
    invoice = savedpaths.rewrite_filter(
        FIELDS, "account.move.line", '[("stored_invoice_id", "<>", False)]', "{}",
        '["stored_invoice_id"]')
    assert _domain(invoice) == [("move_id.move_type", "in", savedpaths.INVOICE_TYPES)]
    assert json.loads(invoice.sort) == ["move_id"]
    reference = savedpaths.rewrite_filter(
        FIELDS, "account.move", '["|", ("number", "ilike", "X"), ("reference", "ilike", "X")]',
        "{}", "[]")
    assert _domain(reference) == ["|", ("name", "ilike", "X"), "|", ("ref", "ilike", "X"),
                                  ("payment_reference", "ilike", "X")]
    rank = savedpaths.rewrite_filter(FIELDS, "res.partner", '[("customer", "=", True)]', "{}",
                                     "[]")
    assert _domain(rank) == [("customer_rank", ">", 0)]


def test_a_domain_is_parsed_never_evaluated_and_groupings_follow():
    domain = ('[("date", ">=", (context_today() - relativedelta(days=7)).strftime("%Y-%m-%d"))]')
    result = savedpaths.rewrite_filter(
        FIELDS, "account.move", domain, "{'group_by': ['date_invoice:month', 'partner_id']}",
        "[]")
    assert result.changed and "context_today()" in result.domain
    assert ast.literal_eval(result.context) == {"group_by": ["invoice_date:month", "partner_id"]}


def test_a_filter_with_nothing_to_rewrite_is_left_byte_for_byte():
    domain = '[("name", "=", "a")]'
    result = savedpaths.rewrite_filter(FIELDS, "account.move", domain, "{}", "[]")
    assert result == savedpaths.FilterResult(domain, "{}", "[]", False)


def test_export_columns_are_renamed_dropped_and_kept_once():
    changes = savedpaths.rewrite_export(FIELDS, "account.journal", [
        (1, "default_debit_account_id/name"), (2, "default_credit_account_id/name"),
        (3, "default_account_id/display_name")])
    assert changes == [(1, "default_account_id/name"), (2, None)]
    assert savedpaths.rewrite_export(FIELDS, "product.template", [
        (1, "name"), (2, "list_price"), (3, "lst_price"), (4, "price")]) == [(3, None), (4, None)]
    # A column no field can replace is kept as it is.
    assert savedpaths.rewrite_export(FIELDS, "account.move", [(1, "reference")]) == []


def test_the_driver_rewrites_after_the_menu_references_and_before_the_checkpoint():
    sh = templates.render_run_migration_sh(MigrationEnv(source="12.0", target="18.0"))
    order = [sh.index(marker) for marker in (
        'mark "18.0" repair menu-references', "<<'ODWG_SAVEDPATHS'",
        'mark "18.0" repair saved-paths', 'checkpoint "18.0"')]
    assert order == sorted(order)
    assert "def rewrite_filter(" in sh and "ODWG_SAVED_PATHS_LIST" in sh
    assert "ODWG_SAVEDPATHS" not in templates.render_run_migration_sh(
        MigrationEnv(source="13.0", target="18.0"))
