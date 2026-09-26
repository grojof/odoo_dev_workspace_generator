"""Configuration the chain changes against the source, put back at the target step.

Three settings, all measured on the first client's database, which OpenUpgrade changes on the way and
the operator never asked for:

- **Return types.** OpenUpgrade 15.0 gives every warehouse a "Returns" operation type and points its
  delivery type's returns at it, and its receipt type's at the delivery type, whatever they were
  (``stock/15.0.1.1/post-migration.py``): a warehouse whose returns went to its own type loses that flow.
  OpenUpgrade 18.0 then creates the multi-step reception types active on every active warehouse
  (``stock/18.0.1.1/post-migration.py`` forces ``active=wh.active``), where Odoo creates them archived
  for a one-step warehouse. And its end-migration fills the default locations 18 requires only on
  active types (``stock/18.0.1.1/end-migration.py`` searches without ``active_test=False``).
- **The invoice-matching rule.** OpenUpgrade 13.0 deletes Odoo's default reconciliation rule
  (``account.reconciliation_model_default_rule``), because a new company gets its rules from the chart
  template, which a migrated company never reloads.
- **Journal mail aliases.** OpenUpgrade 13.0 recreates each journal's alias, passing its old name in a
  ``vals`` argument 13.0 ignores (``account/13.0.1.1/end-migration.py``), so the alias takes the
  journal's name instead.

At the source restore the driver keeps what it needs: every operation type's return type, the
reconciliation rules, and each journal's alias name. At the target step, the target's own Odoo puts back
the return types, archives the types the chain created that nothing uses, gives archived types the
default locations Odoo computes, recreates a deleted default rule with the source's values (mapped as
OpenUpgrade 15.0 maps them), and gives aliases their source names. Everything is listed.

Pure: this module holds SQL and the shell script; the migration driver runs them.
"""

from __future__ import annotations

KEPT_TYPES = "odwg_kept_picking_type"
KEPT_ALIASES = "odwg_kept_journal_alias"
KEPT_RULES = "odwg_kept_reconcile_model"
#: Odoo's default rule up to 12.0, which OpenUpgrade 13.0 deletes.
DEFAULT_RULE = "account.reconciliation_model_default_rule"
#: The script reads 18.0 fields (``default_location_*_id`` required, ``allow_payment_tolerance``).
FIRST_TARGET = 18


def applies(source_major: int, target_major: int) -> bool:
    return source_major < FIRST_TARGET <= target_major


def keep_sql() -> str:
    """Run on the restored source, into tables of the tool's own."""
    return f"""\
DO $odwg$
BEGIN
  DROP TABLE IF EXISTS {KEPT_TYPES}, {KEPT_ALIASES}, {KEPT_RULES};
  IF to_regclass('stock_picking_type') IS NOT NULL THEN
    CREATE TABLE {KEPT_TYPES} AS SELECT id, return_picking_type_id FROM stock_picking_type;
  ELSE
    CREATE TABLE {KEPT_TYPES} (id integer, return_picking_type_id integer);
  END IF;
  IF (SELECT count(*) FROM information_schema.columns WHERE table_schema = current_schema()
      AND table_name = 'account_journal' AND column_name = 'alias_id') = 1 THEN
    CREATE TABLE {KEPT_ALIASES} AS SELECT j.id AS journal_id, a.alias_name
      FROM account_journal j JOIN mail_alias a ON a.id = j.alias_id
      WHERE a.alias_name IS NOT NULL;
  ELSE
    CREATE TABLE {KEPT_ALIASES} (journal_id integer, alias_name varchar);
  END IF;
  IF to_regclass('account_reconcile_model') IS NOT NULL THEN
    CREATE TABLE {KEPT_RULES} AS SELECT m.*, d.module || '.' || d.name AS odwg_xmlid
      FROM account_reconcile_model m LEFT JOIN ir_model_data d
        ON d.model = 'account.reconcile.model' AND d.res_id = m.id;
  END IF;
  RAISE NOTICE '[keep] source configuration: % operation types, % journal aliases',
    (SELECT count(*) FROM {KEPT_TYPES}), (SELECT count(*) FROM {KEPT_ALIASES});
END
$odwg$;
"""


#: Run by the target's ``odoo-bin shell``. Appends ``kind<TAB>id<TAB>detail`` to
#: ``$ODWG_CONFIG_LIST``. The operation types' links are SQL; everything else goes through the ORM.
RESTORE = f"""\
import os
cr = env.cr
listed = []

def rows(sql, params=None):
    cr.execute(sql, params or [])
    return cr.fetchall()

def kept(table):
    return rows("SELECT to_regclass(%s) IS NOT NULL", [table])[0][0]

if kept({KEPT_TYPES!r}):
    # Each existing type's return type, as the source had it, where that type still exists.
    for tid, old, new in rows(
            "UPDATE stock_picking_type t SET return_picking_type_id = k.return_picking_type_id "
            "FROM {KEPT_TYPES} k, stock_picking_type b WHERE t.id = k.id AND b.id = t.id "
            "AND t.return_picking_type_id IS DISTINCT FROM k.return_picking_type_id "
            "AND (k.return_picking_type_id IS NULL OR EXISTS (SELECT 1 FROM stock_picking_type r "
            "WHERE r.id = k.return_picking_type_id)) "
            "RETURNING t.id, b.return_picking_type_id, t.return_picking_type_id"):
        listed.append(("return-type", tid, "return type %s -> %s (as in the source)" % (old, new)))
    # Types the chain created: newer than every source type, on a warehouse. Archived when
    # nothing but the warehouse and other created types points at them.
    top = rows("SELECT coalesce(max(id), 0) FROM {KEPT_TYPES}")[0][0]
    created = [r[0] for r in rows("SELECT id FROM stock_picking_type WHERE id > %s "
                                  "AND warehouse_id IS NOT NULL AND active", [top])]
    refs = rows("SELECT c.conrelid::regclass::text, a.attname FROM pg_constraint c "
                "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1] "
                "WHERE c.contype = 'f' AND c.confrelid = 'stock_picking_type'::regclass "
                "AND c.conrelid::regclass::text <> 'stock_warehouse'")
    used = set()
    for table, column in refs:
        extra = " AND t.id <= %s" % top if table == "stock_picking_type" else ""
        cr.execute('SELECT DISTINCT t."%s" FROM "%s" t WHERE t."%s" = ANY(%%s)%s'
                   % (column, table, column, extra), [created])
        used |= {{r[0] for r in cr.fetchall()}}
    archive = [t for t in created if t not in used]
    if archive:
        cr.execute("UPDATE stock_picking_type SET active = false WHERE id = ANY(%s)", [archive])
    for tid in archive:
        listed.append(("type-archived", tid, "created by the chain, used by nothing"))
    for tid in sorted(set(created) & used):
        listed.append(("type-kept", tid, "created by the chain, already in use"))
    # Archived types without the default locations 18 requires: Odoo's own computes, on the
    # missing field only.
    Type = env["stock.picking.type"].sudo().with_context(active_test=False)
    for field in ("default_location_src_id", "default_location_dest_id"):
        missing = Type.search([(field, "=", False)])
        if missing:
            env.add_to_compute(Type._fields[field], missing)
            env.flush_all()
            for pt in missing:
                listed.append(("default-location", pt.id, "%s -> %s" % (field, pt[field].id or "none")))

if kept({KEPT_RULES!r}):
    Rule = env["account.reconcile.model"].sudo().with_context(active_test=False)
    for rid, company, name, sequence, auto, nature, currency, total, param, partner in rows(
            "SELECT id, company_id, name, sequence, auto_reconcile, match_nature, "
            "match_same_currency, match_total_amount, match_total_amount_param, match_partner "
            "FROM {KEPT_RULES} WHERE odwg_xmlid = %s", [{DEFAULT_RULE!r}]):
        if Rule.search_count([("company_id", "=", company), ("rule_type", "=", "invoice_matching")]):
            continue
        # The source's own values, with the fields OpenUpgrade 15.0 renames and inverts
        # (account/15.0.1.2/pre-migration.py): tolerance param becomes 100 - param.
        rule = Rule.create({{
            "name": name, "sequence": sequence, "company_id": company,
            "rule_type": "invoice_matching", "auto_reconcile": auto, "match_nature": nature,
            "match_same_currency": currency, "match_partner": partner,
            "allow_payment_tolerance": total, "payment_tolerance_type": "percentage",
            "payment_tolerance_param": 100.0 - (param or 0.0), "matching_order": "old_first",
        }})
        listed.append(("rule-recreated", rule.id, "%s (source rule %s, auto-validate %s)"
                       % (name, rid, auto)))

if kept({KEPT_ALIASES!r}):
    Journal = env["account.journal"].sudo().with_context(active_test=False)
    for journal_id, name in rows("SELECT journal_id, alias_name FROM {KEPT_ALIASES}"):
        journal = Journal.browse(journal_id).exists()
        if not journal or not journal.alias_id or journal.alias_id.alias_name == name:
            continue
        before = journal.alias_id.alias_name
        journal.alias_id.write({{"alias_name": name}})
        listed.append(("alias", journal.id, "%s -> %s (source: %s)"
                       % (before, journal.alias_id.alias_name, name)))

env.flush_all()
with open(os.environ["ODWG_CONFIG_LIST"], "a", encoding="utf-8") as out:
    for kind, rid, detail in listed:
        out.write("%s\\t%s\\t%s\\n" % (kind, rid, detail))
cr.commit()
counts = {{}}
for kind, *_ in listed:
    counts[kind] = counts.get(kind, 0) + 1
print("[repair] source configuration: %s" % (", ".join(
    "%s %d" % item for item in sorted(counts.items())) or "nothing to put back"))
"""
