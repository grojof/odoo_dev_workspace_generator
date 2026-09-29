"""Closed periods, as the repairs that rewrite journal items respect them.

A company closes a period with its lock dates: ``fiscalyear_lock_date`` (no one posts on or before it)
and ``tax_lock_date`` (its taxes are declared). OpenUpgrade's maintainers advise against changing
closed fiscal years (OCA/OpenUpgrade#3054), and OCA's ``account_chart_update`` retags taxes, never
past journal items. The repairs that rewrite journal items therefore leave every move dated on or
before the later of the two dates. Both columns exist from 14.0; with neither set, no period is
closed.

Pure: SQL fragments; the migration driver runs them.
"""

from __future__ import annotations


def after_lock(move: str = "m") -> str:
    """A condition true when the move aliased ``move`` is dated after its company's lock dates."""
    return (f"{move}.date > coalesce((SELECT greatest(c.fiscalyear_lock_date, c.tax_lock_date) "
            f"FROM res_company c WHERE c.id = {move}.company_id), '-infinity'::date)")
