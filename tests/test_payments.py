"""The migrated payments' repair: when it applies, what its SQL guards, and where the driver runs it."""

from __future__ import annotations

from odoo_dwg import payments, templates
from odoo_dwg.models import MigrationEnv


def test_it_applies_to_a_chain_that_crosses_18():
    assert payments.applies(12, 18) and payments.applies(17, 19)
    assert not payments.applies(12, 17) and not payments.applies(18, 19)


def test_the_sql_keeps_a_duplicate_anything_else_points_at():
    sql = payments.repair_sql()
    assert sql.startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;")
    # Every foreign key to a payment is checked, except its own links.
    assert "c.confrelid = 'account_payment'::regclass" in sql
    assert "NOT IN ('account_move__account_payment', 'account_payment_account_payment_line_rel')" in sql
    assert "r.invoice_id <> d.move" in sql
    assert "a payment line its twin lacks" in sql and "messages or attachments" in sql
    # The payment to keep is on its order's own entry, and only when there is exactly one.
    assert "coalesce(m.payment_order_id = p.payment_order_id, false) AS own" in sql
    assert "HAVING count(*) = 1)" in sql


def test_a_journal_comes_only_from_the_order_and_only_when_one_method_line_fits():
    sql = payments.repair_sql()
    assert "j.type IN ('bank', 'cash', 'credit')" in sql
    assert "ml.payment_method_id = p.payment_method_id" in sql
    assert "GROUP BY p.id, o.journal_id HAVING count(*) = 1" in sql
    assert "'no-journal'" in sql


def test_the_recompute_is_odoos_own_and_gives_up_on_any_journal_item_change():
    script = payments.RECOMPUTE
    compile(script, "recompute", "exec")
    assert "env.add_to_compute(Payment._fields[name], payments)" in script
    assert 'env.add_to_compute(Move._fields["payment_state"], invoices)' in script
    assert ".write({" not in script and "Payment.write" not in script
    assert script.index("fingerprint() != before") < script.index("cr.commit()")
    assert "cr.rollback()" in script and "for rounds in range(1, 6)" in script


def _driver(source: str = "12.0", target: str = "18.0") -> str:
    return templates.render_run_migration_sh(MigrationEnv(source=source, target=target))


def test_the_target_step_repairs_payments_after_the_grouped_items_and_before_its_checkpoint():
    sh = _driver()
    order = [sh.index(marker) for marker in (
        'mark "18.0" repair grouped-invoice-items', "<<'ODWG_PAYMENTS'", "<<'ODWG_PAYSTATE'",
        'mark "18.0" repair payments', 'checkpoint "18.0"')]
    assert order == sorted(order)
    assert "ODWG_PAYMENTS_LIST=" in sh and "18.0-payments-repaired.tsv" in sh
    assert sh.count("<<'ODWG_PAYMENTS'") == 1


def test_a_chain_that_stops_before_18_has_no_payments_repair():
    assert "ODWG_PAYMENTS" not in _driver(target="17.0")
