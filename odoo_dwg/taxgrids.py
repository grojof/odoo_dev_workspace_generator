"""Tax grids (tax tags), refreshed from the chart template after a chain that crosses 17.0.

From 17.0 a localisation's tax report generates signed tags (``+mod303[01]``, ``-mod303[01]``) and its tax
templates reference them; a database migrated from an older version still has the unsigned tags of its
first chart on every tax repartition line and on every journal item. The native step that retags existing
taxes is the chart template's reload (``l10n_es`` does it in ``migrations/5.4/end-migrate.py``), and
OpenUpgrade 17.0 turns it off (``openupgrade_framework/odoo_patch/odoo/modules/migration.py``); its own
script then tries to delete the old tags, which foreign keys refuse. New invoices in 18 would carry the
old grids, which no 18 report reads.

At the target step, the target's own Odoo:

1. runs the chart template's reload restricted to taxes (``_pre_reload_data`` then ``_load_data`` on the
   template's ``account.tax`` data): for a tax whose template is unchanged, only its repartition lines'
   tags are set from the template; a tax with no template, or a changed one, is left and listed;
2. recomputes the tax tags of every journal item of an open period (``lockdates.py``) from its
   repartition line (a tax line) and from the base repartition lines of its taxes for the document's type
   (a base line), as Odoo sets them when it posts; journal items of plain entries, whose type Odoo derives
   from more than the move, are left and counted. A closed period's items keep their tags, as OCA's
   ``account_chart_update`` leaves them: its taxes are declared;
3. archives the tax tags nothing uses any more and no tax report generates.

No amount moves: every journal item's amounts are fingerprinted before and after, and any difference
rolls it all back.

Pure: this module holds the shell script; the migration driver runs it.
"""

from __future__ import annotations

from .lockdates import after_lock

#: The version whose tax reports generate the signed tags.
FROM_STEP = 17


def applies(source_major: int, target_major: int) -> bool:
    return source_major < FROM_STEP <= target_major


#: Journal items' tags as Odoo sets them: a tax line's from its repartition line, a base line's
#: from its taxes' base repartition lines for the document's type. Plain entries, and closed
#: periods, are left.
_RECOMPUTE_SQL = f"""
CREATE TEMP TABLE odwg_grid_scope AS
  SELECT l.id FROM account_move_line l JOIN account_move m ON m.id = l.move_id
  WHERE m.move_type <> 'entry' AND {after_lock("m")} AND (l.tax_repartition_line_id IS NOT NULL
    OR EXISTS (SELECT 1 FROM account_move_line_account_tax_rel x
               WHERE x.account_move_line_id = l.id));
CREATE TEMP TABLE odwg_grid_new AS
  SELECT l.id AS aml, r.account_account_tag_id AS tag
  FROM account_move_line l JOIN odwg_grid_scope s ON s.id = l.id
  JOIN account_account_tag_account_tax_repartition_line_rel r
    ON r.account_tax_repartition_line_id = l.tax_repartition_line_id
  UNION
  SELECT l.id, r.account_account_tag_id
  FROM account_move_line l JOIN odwg_grid_scope s ON s.id = l.id
  JOIN account_move m ON m.id = l.move_id
  JOIN account_move_line_account_tax_rel x ON x.account_move_line_id = l.id
  JOIN account_tax_repartition_line rl ON rl.tax_id = x.account_tax_id
   AND rl.repartition_type = 'base'
   AND rl.document_type = CASE WHEN m.move_type IN ('out_refund', 'in_refund')
                               THEN 'refund' ELSE 'invoice' END
  JOIN account_account_tag_account_tax_repartition_line_rel r
    ON r.account_tax_repartition_line_id = rl.id;
CREATE TEMP TABLE odwg_grid_old AS
  SELECT t.account_move_line_id AS aml, t.account_account_tag_id AS tag
  FROM account_account_tag_account_move_line_rel t
  JOIN odwg_grid_scope s ON s.id = t.account_move_line_id
  JOIN account_account_tag g ON g.id = t.account_account_tag_id AND g.applicability = 'taxes';
DELETE FROM account_account_tag_account_move_line_rel t USING odwg_grid_old o
  WHERE t.account_move_line_id = o.aml AND t.account_account_tag_id = o.tag;
INSERT INTO account_account_tag_account_move_line_rel (account_move_line_id, account_account_tag_id)
  SELECT aml, tag FROM odwg_grid_new ON CONFLICT DO NOTHING;
"""

#: Journal items with taxes that a closed period keeps as they are.
_CLOSED_SQL = f"""
SELECT count(*) FROM account_move_line l JOIN account_move m ON m.id = l.move_id
WHERE m.move_type <> 'entry' AND NOT {after_lock("m")} AND (l.tax_repartition_line_id IS NOT NULL
  OR EXISTS (SELECT 1 FROM account_move_line_account_tax_rel x WHERE x.account_move_line_id = l.id))
"""

#: Tax tags no repartition line or journal item uses, and no tax report generates.
_ARCHIVE_SQL = """
UPDATE account_account_tag g SET active = false
WHERE g.applicability = 'taxes' AND g.active
  AND NOT EXISTS (SELECT 1 FROM account_account_tag_account_tax_repartition_line_rel r
                  WHERE r.account_account_tag_id = g.id)
  AND NOT EXISTS (SELECT 1 FROM account_account_tag_account_move_line_rel t
                  WHERE t.account_account_tag_id = g.id)
  AND g.name->>'en_US' NOT IN (
    SELECT sign || e.formula FROM account_report_expression e, (VALUES ('+'), ('-')) s(sign)
    WHERE e.engine = 'tax_tags')
RETURNING g.id, g.name->>'en_US'
"""

#: Run by the target's ``odoo-bin shell``. Appends ``kind<TAB>id<TAB>detail`` to
#: ``$ODWG_TAXGRIDS_LIST``.
REFRESH = f"""\
import os
cr = env.cr
AMOUNTS = ("SELECT md5(string_agg(md5(concat_ws('|', id, account_id, debit, credit, balance, "
           "amount_currency, tax_base_amount, tax_line_id, tax_repartition_line_id, "
           "tax_tag_invert)), '' ORDER BY id)) FROM account_move_line")

def rows(sql, params=None):
    cr.execute(sql, params or [])
    return cr.fetchall()

def rep_tags():
    return {{rid: tuple(sorted(tags or [])) for rid, tags in rows(
        "SELECT l.id, array_agg(r.account_account_tag_id) FROM account_tax_repartition_line l "
        "LEFT JOIN account_account_tag_account_tax_repartition_line_rel r "
        "ON r.account_tax_repartition_line_id = l.id GROUP BY l.id")}}

before = rows(AMOUNTS)[0][0]
old_rep = rep_tags()
listed = []
for company in env["res.company"].sudo().search([("chart_template", "!=", False)]):
    CT = env["account.chart.template"].sudo().with_context(
        default_company_id=company.id, allowed_company_ids=[company.id], tracking_disable=True,
        delay_account_group_sync=True, lang="en_US", chart_template_load=True)
    company = CT.env["res.company"].browse(company.id)
    data = CT._get_chart_template_data(company.chart_template)
    template_data = data.pop("template_data")
    data = {{"account.tax": data.get("account.tax", {{}})}}
    # The reload's own rule: an existing tax whose template is unchanged gets only its
    # repartition lines' tags; anything else is skipped.
    CT._pre_reload_data(company, template_data, data, force_create=False)
    CT._load_data(data)
    retagged = {{CT.ref(xmlid).id for xmlid in data["account.tax"]}}
    for tax in env["account.tax"].sudo().with_context(active_test=False).search(
            [("company_id", "=", company.id)]):
        if tax.id not in retagged:
            listed.append(("tax-left", tax.id, "%s: no unchanged template" % tax.name))
env.flush_all()
new_rep = rep_tags()
for rid in sorted(new_rep):
    if old_rep.get(rid) != new_rep[rid]:
        listed.append(("repartition", rid, "%s -> %s" % (list(old_rep.get(rid, ())),
                                                         list(new_rep[rid]))))
cr.execute({_RECOMPUTE_SQL!r})
changed = rows("SELECT count(DISTINCT aml) FROM (SELECT * FROM odwg_grid_old EXCEPT "
               "SELECT * FROM odwg_grid_new UNION SELECT * FROM odwg_grid_new EXCEPT "
               "SELECT * FROM odwg_grid_old) d")[0][0]
entries = rows("SELECT count(*) FROM account_move_line l JOIN account_move m ON m.id = l.move_id "
               "WHERE m.move_type = 'entry' AND (l.tax_repartition_line_id IS NOT NULL OR EXISTS "
               "(SELECT 1 FROM account_move_line_account_tax_rel x "
               "WHERE x.account_move_line_id = l.id))")[0][0]
closed = rows({_CLOSED_SQL!r})[0][0]
for tag_id, name in rows({_ARCHIVE_SQL!r}):
    listed.append(("tag-archived", tag_id, name))
if rows(AMOUNTS)[0][0] != before:
    cr.rollback()
    raise SystemExit("[repair] tax grids: a journal item's amount would change; nothing kept")
with open(os.environ["ODWG_TAXGRIDS_LIST"], "a", encoding="utf-8") as out:
    for kind, rid, detail in listed:
        out.write("%s\\t%s\\t%s\\n" % (kind, rid, detail))
    out.write("journal-items\\t-\\t%d with other tax grids; %d of plain entries left; %d of "
              "closed periods kept\\n" % (changed, entries, closed))
cr.commit()
print("[repair] tax grids: %d repartition line(s) retagged, %d tax(es) left, %d journal item(s) "
      "regridded, %d of plain entries left, %d of closed periods kept, %d tag(s) archived" % (
          sum(1 for k, *_ in listed if k == "repartition"),
          sum(1 for k, *_ in listed if k == "tax-left"), changed, entries, closed,
          sum(1 for k, *_ in listed if k == "tag-archived")))
"""
