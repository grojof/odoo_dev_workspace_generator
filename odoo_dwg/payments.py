"""Migrated payments, repaired at the target step.

Three defects no step repairs, all measured on the first client's database:

- OCA ``account_payment_order`` 14.0 inserts one payment per bank payment line with a ``LEFT JOIN`` on
  the journal items that carry the line (``migrations/14.0.2.0.0/post-migration.py``). An operator's own
  entry that repeats a line's reference (an expense or reversal of a remittance) yields a second payment
  for the same line. No journal item points at it; every payment list counts it.
- OpenUpgrade 18.0 fills ``account_payment.journal_id`` from the entry's journal only when that is a
  bank, cash or credit journal (``account/18.0.1.3/pre-migration.py``). A payment order posted through a
  miscellaneous journal leaves its payments with none, though 18 requires it.
- The same script sets ``state`` to ``paid`` only when the entry's ``payment_state`` is ``paid``, which a
  payment's entry never is in 17: every posted payment stays ``in_process``, and nothing recomputes it.

The duplicates and journals are SQL (an ORM write of a payment's journal rewrites its entry); the
recompute is Odoo's own, run by the target's ``odoo-bin shell``, and gives up when any journal item's
account, amount or reconciliation would change.

Pure: this module holds the SQL and the shell script; the migration driver runs them.
"""

from __future__ import annotations

#: The step whose OpenUpgrade scripts leave the journals and states this repairs.
FROM_STEP = 18


def applies(source_major: int, target_major: int) -> bool:
    """Whether the chain crosses 18.0."""
    return source_major < FROM_STEP <= target_major


#: Every foreign key to ``account_payment`` must be empty for a duplicate, except its own links:
#: to its own entry, and to payment lines its kept twin has too.
_OWN_LINKS = ("account_move__account_payment", "account_payment_account_payment_line_rel")


def repair_sql() -> str:
    """Remove the duplicate payment-order payments, then give the journal-less payments their
    order's journal. One transaction; prints ``kind<TAB>payment<TAB>detail`` per payment it
    touched or left."""
    own_links = ", ".join(f"'{t}'" for t in _OWN_LINKS)
    return f"""\
BEGIN;
CREATE TEMP TABLE odwg_pay_list (kind text, payment_id integer, detail text);
CREATE TEMP TABLE odwg_pay_dup (id integer PRIMARY KEY, line integer, keeper integer, move integer);
DO $odwg$
DECLARE
  fk record;
  n integer;
BEGIN
  IF (SELECT count(*) FROM information_schema.columns WHERE table_schema = current_schema()
      AND ((table_name = 'account_payment'
            AND column_name IN ('old_bank_payment_line_id', 'payment_order_id'))
        OR (table_name = 'account_move' AND column_name = 'payment_order_id'))) = 3 THEN
    -- A bank payment line with several payments keeps the one on its order's own entry.
    INSERT INTO odwg_pay_dup
    WITH k AS (
      SELECT p.id, p.old_bank_payment_line_id AS line, p.move_id,
             coalesce(m.payment_order_id = p.payment_order_id, false) AS own
      FROM account_payment p JOIN account_move m ON m.id = p.move_id
      WHERE p.old_bank_payment_line_id IN (
        SELECT old_bank_payment_line_id FROM account_payment
        WHERE old_bank_payment_line_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1)),
    keep AS (SELECT line, min(id) AS keeper FROM k WHERE own GROUP BY line HAVING count(*) = 1)
    SELECT k.id, k.line, keep.keeper, k.move_id FROM k JOIN keep ON keep.line = k.line
    WHERE NOT k.own;
    -- Anything pointing at a duplicate keeps it, but its own links: its entry, and the
    -- payment lines its kept twin has as well.
    FOR fk IN
      SELECT c.conrelid::regclass::text AS tbl, a.attname AS col
      FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
      WHERE c.contype = 'f' AND c.confrelid = 'account_payment'::regclass
        AND c.conrelid::regclass::text NOT IN ({own_links})
    LOOP
      EXECUTE format('INSERT INTO odwg_pay_list SELECT %L, d.id, %L FROM odwg_pay_dup d '
                     'WHERE EXISTS (SELECT 1 FROM %s t WHERE t.%I = d.id)',
                     'duplicate-kept', 'referenced by ' || fk.tbl || '.' || fk.col, fk.tbl, fk.col);
    END LOOP;
    INSERT INTO odwg_pay_list SELECT 'duplicate-kept', d.id, 'linked to another entry'
      FROM odwg_pay_dup d JOIN account_move__account_payment r ON r.payment_id = d.id
      WHERE r.invoice_id <> d.move;
    IF to_regclass('account_payment_account_payment_line_rel') IS NOT NULL THEN
      INSERT INTO odwg_pay_list SELECT 'duplicate-kept', d.id, 'a payment line its twin lacks'
        FROM odwg_pay_dup d JOIN account_payment_account_payment_line_rel r
          ON r.account_payment_id = d.id
        WHERE NOT EXISTS (SELECT 1 FROM account_payment_account_payment_line_rel t
                          WHERE t.account_payment_id = d.keeper
                            AND t.account_payment_line_id = r.account_payment_line_id);
    END IF;
    INSERT INTO odwg_pay_list SELECT 'duplicate-kept', d.id, 'messages or attachments'
      FROM odwg_pay_dup d
      WHERE EXISTS (SELECT 1 FROM mail_message WHERE model = 'account.payment' AND res_id = d.id)
         OR EXISTS (SELECT 1 FROM ir_attachment
                    WHERE res_model = 'account.payment' AND res_id = d.id);
    DELETE FROM odwg_pay_dup WHERE id IN (
      SELECT payment_id FROM odwg_pay_list WHERE kind = 'duplicate-kept');
    INSERT INTO odwg_pay_list SELECT 'removed', d.id,
        'bank payment line ' || d.line || ', on entry ' || d.move || '; kept ' || d.keeper
      FROM odwg_pay_dup d;
    DELETE FROM mail_followers WHERE res_model = 'account.payment'
      AND res_id IN (SELECT id FROM odwg_pay_dup);
    DELETE FROM account_payment WHERE id IN (SELECT id FROM odwg_pay_dup);
    GET DIAGNOSTICS n = ROW_COUNT;
    RAISE NOTICE '[repair] payments: % duplicate payment-order payment(s) removed', n;
  ELSE
    RAISE NOTICE '[repair] payments: no payment-order payments';
  END IF;

  -- A payment with no journal takes its order's, when that is a bank, cash or credit journal
  -- with exactly one method line for the payment's method.
  IF (SELECT count(*) FROM information_schema.columns WHERE table_schema = current_schema()
      AND table_name = 'account_payment' AND column_name = 'payment_order_id') = 1 THEN
    WITH fit AS (
      SELECT p.id, o.journal_id, min(ml.id) AS line
      FROM account_payment p
      JOIN account_payment_order o ON o.id = p.payment_order_id
      JOIN account_journal j ON j.id = o.journal_id AND j.type IN ('bank', 'cash', 'credit')
      JOIN account_payment_method_line ml
        ON ml.journal_id = o.journal_id AND ml.payment_method_id = p.payment_method_id
      WHERE p.journal_id IS NULL
      GROUP BY p.id, o.journal_id HAVING count(*) = 1),
    done AS (
      UPDATE account_payment p SET journal_id = fit.journal_id, payment_method_line_id = fit.line
      FROM fit WHERE p.id = fit.id RETURNING p.id, fit.journal_id)
    INSERT INTO odwg_pay_list SELECT 'journal', id, 'journal ' || journal_id FROM done;
  END IF;
  INSERT INTO odwg_pay_list SELECT 'no-journal', id, 'no payment order journal fits'
    FROM account_payment WHERE journal_id IS NULL;
END
$odwg$;
SELECT kind, payment_id, detail FROM odwg_pay_list ORDER BY kind, payment_id;
COMMIT;
"""


#: Run by the target's ``odoo-bin shell``, after :func:`repair_sql`: Odoo's own computes of every
#: posted payment's state and reconciliation flags, then of every posted invoice's payment status,
#: through ``add_to_compute`` (no ``write``: no tracking, no entry synchronisation). The journal
#: items and entries are fingerprinted before and after: any difference rolls it all back. Appends
#: ``kind<TAB>id<TAB>detail`` to ``$ODWG_PAYMENTS_LIST``.
RECOMPUTE = """\
import os
cr = env.cr
LINES = ("SELECT md5(string_agg(md5(concat_ws('|', id, account_id, debit, credit, balance, "
         "amount_currency, amount_residual, amount_residual_currency, reconciled, "
         "full_reconcile_id)), '' ORDER BY id)) FROM account_move_line")
MOVES = ("SELECT md5(string_agg(md5(concat_ws('|', id, name, journal_id, state, date, "
         "amount_total, amount_residual)), '' ORDER BY id)) FROM account_move")

def fingerprint():
    cr.execute(LINES)
    lines = cr.fetchone()[0]
    cr.execute(MOVES)
    return lines, cr.fetchone()[0]

def values(table, columns, where):
    cr.execute("SELECT id, %s FROM %s WHERE %s" % (", ".join(columns), table, where))
    return {row[0]: row[1:] for row in cr.fetchall()}

before = fingerprint()
Payment = env["account.payment"].sudo()
Move = env["account.move"].sudo()
pay_fields = ("state", "is_reconciled", "is_matched")
posted = "state IN ('in_process', 'paid')"
old_pay = values("account_payment", pay_fields, posted)
payments = Payment.browse(list(old_pay))
invoice = "state = 'posted' AND move_type IN %s" % (tuple(Move.get_invoice_types(True)),)
old_inv = values("account_move", ("name", "payment_state"), invoice)
invoices = Move.browse(list(old_inv))
# A payment's state reads its invoices' payment status and an invoice's reads its payments';
# a recompute does not carry one into the other, so both run again until neither changes.
last = None
for rounds in range(1, 6):
    for name in pay_fields:
        env.add_to_compute(Payment._fields[name], payments)
    env.flush_all()
    env.add_to_compute(Move._fields["payment_state"], invoices)
    env.flush_all()
    now = (values("account_payment", pay_fields, posted),
           values("account_move", ("payment_state",), invoice))
    if now == last:
        break
    last = now
else:
    cr.rollback()
    raise SystemExit("[repair] payments: the states do not settle after 5 rounds; nothing kept")
print("[repair] payments: states settled after %d round(s)" % (rounds - 1))
if fingerprint() != before:
    cr.rollback()
    raise SystemExit("[repair] payments: a journal item or entry would change; nothing kept")
new_pay = values("account_payment", pay_fields, posted)
new_inv = values("account_move", ("name", "payment_state"), invoice)
changed = {}
with open(os.environ["ODWG_PAYMENTS_LIST"], "a", encoding="utf-8") as out:
    for pid in sorted(old_pay):
        old, new = old_pay[pid], new_pay.get(pid, old_pay[pid])
        if old != new:
            out.write("payment\\t%s\\t%s\\n" % (pid, " ".join(
                "%s %s->%s" % (f, o, n) for f, o, n in zip(pay_fields, old, new) if o != n)))
            for f, o, n in zip(pay_fields, old, new):
                if o != n:
                    changed[(f, o, n)] = changed.get((f, o, n), 0) + 1
    moved = 0
    for mid in sorted(old_inv):
        name, old = old_inv[mid]
        new = new_inv.get(mid, old_inv[mid])[1]
        if old != new:
            moved += 1
            out.write("invoice\\t%s\\t%s %s->%s\\n" % (mid, name, old, new))
cr.commit()
for (f, o, n), count in sorted(changed.items(), key=str):
    print("[repair] payments: %s %s -> %s on %d" % (f, o, n, count))
print("[repair] payments: %d invoice(s) changed payment status" % moved)
"""
