"""Closed periods, as the repairs that rewrite journal items respect them."""

from __future__ import annotations

from odoo_dwg import lockdates


def test_a_move_is_after_the_later_of_its_companys_lock_dates():
    condition = lockdates.after_lock("mv")
    assert condition.startswith("mv.date > coalesce(")
    assert "greatest(c.fiscalyear_lock_date, c.tax_lock_date)" in condition
    assert "c.id = mv.company_id" in condition
    # No lock date: every period is open.
    assert condition.endswith("'-infinity'::date)")
