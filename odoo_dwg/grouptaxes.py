"""Group taxes turned into one tax by the 13.0 step: their repartition lines' accounts.

Up to 12.0 a localisation can model a reverse charge as a group tax with two children, one per
side, and the accounts are the children's: the group holds none. OpenUpgrade 13.0 (``l10n_es``
13.0.4.0, ``use_new_taxes_and_repartition_lines_on_move_lines``) gives such a group its own
repartition lines and takes their account from the group, so the tax lines have none. The journal
items that existed keep their accounts; a bill posted after the migration puts both tax amounts on
the expense account of its line.

OCA's ``account_chart_update`` fills the template's accounts when it is run at 13.0. A chain that
goes on without it carries the lines without account, and at 18.0 the wizard cannot repair a tax
already used. Proposed upstream as OCA/OpenUpgrade#6047; with it, this finds nothing to repair.

Right after the 13.0 step, each tax repartition line of a former group takes the account of its
child's repartition line, matched by document, repartition type and sign, as OpenUpgrade itself
matches the journal items. Only lines without an account are written, so an account the database
already has stays.

Pure: this module holds SQL; the migration driver runs it with ``psql``.
"""

from __future__ import annotations

#: The source up to which a localisation's group taxes hold their accounts on their children.
SOURCE_MAX_MAJOR = 12
#: The step that turns them into one tax, and after which the accounts are set.
REPAIR_STEP = "13.0"


def applies(source_major: int) -> bool:
    return source_major <= SOURCE_MAX_MAJOR


def repair_sql() -> str:
    """The repair, for ``psql -X -q -At -F<tab> -v ON_ERROR_STOP=1``.

    The lines it wrote go to stdout: tax id, tax, document, factor and account code."""
    return """\
WITH fixed AS (
  UPDATE account_tax_repartition_line parent
  SET account_id = child.account_id
  FROM account_tax_repartition_line child
  JOIN account_tax tax ON tax.id = COALESCE(child.invoice_tax_id, child.refund_tax_id)
  JOIN account_tax_filiation_rel rel ON rel.child_tax = tax.id
  WHERE COALESCE(parent.invoice_tax_id, parent.refund_tax_id) = rel.parent_tax
    AND (parent.invoice_tax_id IS NULL) = (child.invoice_tax_id IS NULL)
    AND parent.repartition_type = 'tax' AND child.repartition_type = 'tax'
    AND SIGN(tax.amount) = SIGN(parent.factor_percent)
    AND parent.account_id IS NULL AND child.account_id IS NOT NULL
  RETURNING rel.parent_tax, parent.invoice_tax_id IS NOT NULL AS invoice,
    parent.factor_percent, parent.account_id)
SELECT f.parent_tax, t.name, CASE WHEN f.invoice THEN 'invoice' ELSE 'refund' END,
  f.factor_percent, a.code
FROM fixed f JOIN account_tax t ON t.id = f.parent_tax
JOIN account_account a ON a.id = f.account_id
ORDER BY f.parent_tax, f.invoice DESC, f.factor_percent DESC;
"""
