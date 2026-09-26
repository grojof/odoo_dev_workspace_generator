"""Stock valuation layers rebuilt by OpenUpgrade 13.0, aligned to on-hand quantity and cost.

Up to 12.0 there are no valuation layers: a product's value is its on-hand quantity times its cost.
OpenUpgrade 13.0 builds the layers by replaying the moves and the price history
(``stock_account/migrations/13.0.1.1/post-migration.py``), and two flaws of that replay leave the
layers' value away from quantity times cost:

- in 12.0 a receipt's own averaged cost is written to the price history a moment before the move is
  done, and the replay counts it once as a manual revaluation of the stock on hand and once more as
  the receipt;
- a receipt that brings negative stock back to zero keeps its whole value on no quantity, and the
  outgoing layers the replay creates never let Odoo's vacuum compensate it.

The layers' quantity can also differ from the stock on hand, where the source's quants and moves
already disagreed. Odoo 18 values a product from its layers, so its valuation screens show neither
the source's figure nor the stock there is.

At the target step, the target's own Odoo adds one layer per product that differs, with the
quantity and value that bring its layers to the stock on hand at its cost, as Odoo does when it
empties and refills a product's stock. Only products whose valuation is periodic: no journal entry is
created, and one that would be stops it all. FIFO and lot-valued products are left and listed.

Pure: this module holds the shell script; the migration driver runs it.
"""

from __future__ import annotations

#: Sources up to this version have no valuation layers; OpenUpgrade 13.0 builds them.
LAST_WITHOUT_LAYERS = 12
#: The Odoo whose valuation rules the script reads (``is_storable``, ``lot_valuated``).
FIRST_TARGET = 18

DESCRIPTION = "Migration: align to on-hand quantity and cost"


def applies(source_major: int, target_major: int) -> bool:
    return source_major <= LAST_WITHOUT_LAYERS and target_major >= FIRST_TARGET


#: Run by the target's ``odoo-bin shell``. Appends ``kind<TAB>product<TAB>detail`` to
#: ``$ODWG_VALUATION_LIST``. Gives up, keeping nothing, if a journal entry appears, a cost changes,
#: or a product it adjusted does not end at on-hand quantity times cost.
ALIGN = f"""\
import os
from collections import defaultdict
from odoo.tools import float_is_zero
cr = env.cr
DESCRIPTION = {DESCRIPTION!r}

def scalar(sql):
    cr.execute(sql)
    return cr.fetchone()[0]

MOVES = "SELECT count(*) FROM account_move"
COSTS = ("SELECT md5(string_agg(concat_ws('|', id, standard_price::text), ',' ORDER BY id)) "
         "FROM product_product")
before = (scalar(MOVES), scalar(COSTS))
listed, adjusted = [], []
for company in env["res.company"].sudo().search([]):
    currency = company.currency_id
    onhand = defaultdict(float)
    quants = env["stock.quant"].sudo().search([
        ("company_id", "=", company.id), ("location_id.usage", "in", ("internal", "transit"))])
    for quant in quants:
        if quant.location_id._should_be_valued() and not quant._should_exclude_for_valuation():
            onhand[quant.product_id.id] += quant.quantity
    cr.execute("SELECT DISTINCT product_id FROM stock_valuation_layer WHERE company_id = %s",
               [company.id])
    ids = {{row[0] for row in cr.fetchall()}} | set(onhand)
    Product = env["product.product"].sudo().with_company(company).with_context(active_test=False)
    vals_list = []
    for product in Product.browse(sorted(ids)).filtered("is_storable"):
        if product.valuation == "real_time":
            listed.append(("left", product, "automated valuation: aligning would post an entry"))
            continue
        if product.cost_method == "fifo" or product.lot_valuated:
            listed.append(("left", product, "FIFO or lot-valued: layers carry their own cost"))
            continue
        quantity = onhand.get(product.id, 0.0)
        target = currency.round(quantity * product.standard_price)
        dq = quantity - product.quantity_svl
        dv = currency.round(target - product.value_svl)
        if float_is_zero(dq, precision_rounding=product.uom_id.rounding) and currency.is_zero(dv):
            continue
        vals = {{"company_id": company.id, "product_id": product.id, "description": DESCRIPTION,
                "quantity": dq, "unit_cost": product.standard_price, "value": dv}}
        if product.cost_method == "average":
            # As emptying and refilling the stock does: the layers before keep nothing to
            # consume, and this one holds what is on hand.
            cr.execute("UPDATE stock_valuation_layer SET remaining_qty = 0, remaining_value = 0 "
                       "WHERE product_id = %s AND company_id = %s "
                       "AND (remaining_qty <> 0 OR remaining_value <> 0)",
                       [product.id, company.id])
            vals.update(remaining_qty=max(quantity, 0.0), remaining_value=max(target, 0.0))
        vals_list.append(vals)
        adjusted.append((company, product, quantity, target, product.quantity_svl,
                         product.value_svl, dq, dv))
    env["stock.valuation.layer"].sudo().create(vals_list)
env.flush_all()
env.invalidate_all()
wrong = []
for company, product, quantity, target, *_ in adjusted:
    product = product.with_company(company)
    if not (float_is_zero(product.quantity_svl - quantity,
                          precision_rounding=product.uom_id.rounding)
            and company.currency_id.is_zero(product.value_svl - target)):
        wrong.append(product.id)
if (scalar(MOVES), scalar(COSTS)) != before or wrong:
    cr.rollback()
    raise SystemExit("[repair] valuation: a journal entry or a cost would change, or products "
                     "%s did not align; nothing kept" % wrong[:10])
with open(os.environ["ODWG_VALUATION_LIST"], "a", encoding="utf-8") as out:
    for company, product, quantity, target, qty_svl, value_svl, dq, dv in adjusted:
        out.write("aligned\\t%s\\t%s: quantity %s -> %s, value %s -> %s (%+.2f)\\n" % (
            product.id, product.default_code or product.display_name, qty_svl, quantity,
            value_svl, target, dv))
    for kind, product, why in listed:
        out.write("%s\\t%s\\t%s\\n" % (kind, product.id, why))
cr.commit()
print("[repair] valuation: %d product(s) aligned to on-hand quantity and cost, %d left, "
      "value %+.2f" % (len(adjusted), len(listed), sum(a[7] for a in adjusted)))
"""
