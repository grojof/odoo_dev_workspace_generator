"""Grouped invoice items, given back to the invoice lines they stand for.

Odoo up to 12.0 can post an invoice with one journal item per account and taxes instead
of one per invoice line. OpenUpgrade 13.0 (``account`` 13.0.1.1, ``migration_invoice_moves``)
keeps such an item, marks it ``exclude_from_invoice_tab`` and inserts the invoice lines it
stands for with a zero balance; 13.0 to 15.0 hide the item. OpenUpgrade 16.0
(``_account_move_fast_fill_display_type``) types it ``product`` without reading that flag,
so from 16.0 the item is an invoice line of its own, carrying the whole amount, and the
real lines carry none.

The repair moves each item's amount to its lines and deletes it, one group at a time: one
move, one account, one set of taxes. It repairs only invoices of open periods, or still open
(``lockdates.py``): an invoice of a closed period keeps OpenUpgrade's result, the grouped item
as a line of its own, as OpenUpgrade's maintainers advise (OCA/OpenUpgrade#3054). Inside a group no account's, partner's or tax's sum
can change, so a declaration filed from the source recomputes the same. It commits only
when its checks hold, and names every group it leaves.

Pure: this module holds SQL; the migration driver runs it with ``psql``.
"""

from __future__ import annotations

from .lockdates import after_lock

#: The source up to which invoices can hold grouped items, and the target from which
#: OpenUpgrade has typed them as product lines.
SOURCE_MAX_MAJOR = 12
TARGET_MIN_MAJOR = 16

#: Tables that hold the line's own attributes: its taxes, its tax tags, and the analytic accounts
#: OCA ``account_financial_report`` stores from its analytic distribution. Kept by each line,
#: never copied to others, and no reason to keep a line out of a repair.
OWN_LINK_TABLES = (
    "account_move_line_account_tax_rel",
    "account_account_tag_account_move_line_rel",
    "account_analytic_account_account_move_line_rel",
)

#: Single references the repair moves to the group's largest line: rows that describe the
#: line's amount, kept once. Any other reference to a grouped item leaves its group as it is.
MOVABLE_REFERENCES = (
    ("account_analytic_line", "move_line_id"),
    ("l10n_es_aeat_mod349_partner_record_detail", "move_line_id"),
    ("l10n_es_aeat_mod349_partner_refund_detail", "refund_line_id"),
)


def applies(source_major: int, target_major: int) -> bool:
    """A chain whose source can group invoice items and whose target types them as lines."""
    return source_major <= SOURCE_MAX_MAJOR and target_major >= TARGET_MIN_MAJOR


def _sql_list(pairs: tuple[tuple[str, str], ...]) -> str:
    return ", ".join(f"('{table}', '{column}')" for table, column in pairs)


def ungroup_sql() -> str:
    """The repair, for ``psql -X -q -At -v ON_ERROR_STOP=1 -f``.

    Progress goes to stderr (notices). The groups left, one per row
    (move id, move, account id, tax ids, grouped amount, reason), go to stdout."""
    own = ", ".join(f"'{table}'" for table in OWN_LINK_TABLES)
    in_scope = after_lock("m")
    movable = _sql_list(MOVABLE_REFERENCES)
    return f"""\
\\set ON_ERROR_STOP 1
SELECT count(*) = 3 AS odwg_ready FROM information_schema.columns
  WHERE table_schema = current_schema() AND table_name = 'account_move_line'
    AND column_name IN ('exclude_from_invoice_tab', 'old_invoice_line_id', 'display_type') \\gset
\\if :odwg_ready
BEGIN;
CREATE TEMP TABLE odwg_left (move_id integer, move_name varchar, account_id integer,
  taxes text, amount numeric, reason text) ON COMMIT DROP;
DO $odwg$
DECLARE
  fk record;
  other_col text;
  removed integer;
  kept integer := 0;
  moved integer;
  restored integer := 0;
BEGIN
  -- Grouped items: an invoice's items OpenUpgrade 13.0 kept outside the invoice tab, with no
  -- invoice line of their own, that 16.0 typed as product lines.
  CREATE TEMP TABLE odwg_g ON COMMIT DROP AS
    SELECT l.id, l.move_id, l.account_id, l.partner_id, l.balance,
      coalesce((SELECT string_agg(r.account_tax_id::text, ',' ORDER BY r.account_tax_id)
                FROM account_move_line_account_tax_rel r WHERE r.account_move_line_id = l.id), '') tk,
      (coalesce(l.reconciled, false) OR coalesce(l.amount_residual, 0) NOT IN (0, l.balance)) settled
    FROM account_move_line l JOIN account_move m ON m.id = l.move_id
    WHERE l.exclude_from_invoice_tab AND l.display_type = 'product' AND l.old_invoice_line_id IS NULL
      AND m.move_type IN ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')
      -- A closed period's invoice keeps OpenUpgrade's result, unless it is still open.
      AND ({in_scope} OR m.amount_residual <> 0);
  SELECT count(DISTINCT l.move_id) INTO kept
    FROM account_move_line l JOIN account_move m ON m.id = l.move_id
    WHERE l.exclude_from_invoice_tab AND l.display_type = 'product' AND l.old_invoice_line_id IS NULL
      AND m.move_type IN ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')
      AND NOT ({in_scope} OR m.amount_residual <> 0);
  IF kept > 0 THEN
    RAISE NOTICE '[repair] grouped invoice items: % paid invoice(s) of closed periods kept as OpenUpgrade left them', kept;
  END IF;
  kept := 0;
  IF NOT EXISTS (SELECT 1 FROM odwg_g) THEN
    RAISE NOTICE '[repair] grouped invoice items: none';
    RETURN;
  END IF;

  -- What points at a journal item: a link table (two columns) is copied from a grouped item to
  -- its lines, a known single reference moves to the largest line, anything else keeps its group.
  CREATE TEMP TABLE odwg_fk (tbl text, col text, other text, kind text) ON COMMIT DROP;
  FOR fk IN
    SELECT cl.relname::text tbl, a.attname::text col, c.conrelid,
      (SELECT count(*) FROM pg_attribute x
        WHERE x.attrelid = c.conrelid AND x.attnum > 0 AND NOT x.attisdropped) ncols
    FROM pg_constraint c
    JOIN pg_class cl ON cl.oid = c.conrelid
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
    WHERE c.contype = 'f' AND c.confrelid = 'account_move_line'::regclass
      AND array_length(c.conkey, 1) = 1
  LOOP
    SELECT x.attname INTO other_col FROM pg_attribute x
      WHERE x.attrelid = fk.conrelid AND x.attnum > 0 AND NOT x.attisdropped AND x.attname <> fk.col
      ORDER BY x.attnum LIMIT 1;
    IF fk.tbl IN ({own}) THEN
      CONTINUE;
    ELSIF (fk.tbl, fk.col) IN ({movable}) THEN
      INSERT INTO odwg_fk VALUES (fk.tbl, fk.col, NULL, 'single');
    ELSIF fk.ncols = 2 AND other_col <> 'id' THEN
      -- A many-to-many table: the line's column and the other record's, nothing else.
      INSERT INTO odwg_fk VALUES (fk.tbl, fk.col, other_col, 'link');
    ELSE
      INSERT INTO odwg_fk VALUES (fk.tbl, fk.col, NULL, 'other');
    END IF;
  END LOOP;

  -- The invoice lines OpenUpgrade 13.0 inserted at a zero amount, keyed on their own taxes.
  CREATE TEMP TABLE odwg_z ON COMMIT DROP AS
    SELECT l.id, l.move_id, l.account_id, coalesce(l.price_subtotal, 0) price_subtotal,
      coalesce((SELECT string_agg(r.account_tax_id::text, ',' ORDER BY r.account_tax_id)
                FROM account_move_line_account_tax_rel r WHERE r.account_move_line_id = l.id), '') cur_tk,
      l.old_invoice_line_id
    FROM account_move_line l
    WHERE l.move_id IN (SELECT move_id FROM odwg_g) AND l.display_type = 'product'
      AND NOT coalesce(l.exclude_from_invoice_tab, false) AND l.old_invoice_line_id IS NOT NULL
      AND l.balance = 0 AND coalesce(l.amount_currency, 0) = 0;
  -- A zero-amount line whose invoice line OpenUpgrade 13.0 matched to a source journal item
  -- (``account_invoice_line.aml_matched``) is that item, reused: it has a history (a
  -- declaration's detail, a VAT book line, an analytic line) that giving it an amount would
  -- falsify. It keeps its zero, and its group is left if it needed it.
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema()
             AND table_name = 'account_invoice_line' AND column_name = 'aml_matched') THEN
    EXECUTE 'DELETE FROM odwg_z z USING account_invoice_line il
              WHERE il.id = z.old_invoice_line_id AND il.aml_matched';
    GET DIAGNOSTICS kept = ROW_COUNT;
  END IF;
  ALTER TABLE odwg_z ADD COLUMN tk text;
  UPDATE odwg_z SET tk = cur_tk;
  CREATE INDEX ON odwg_g (id);
  CREATE INDEX ON odwg_g (move_id, account_id, tk);
  CREATE INDEX ON odwg_z (id);
  CREATE INDEX ON odwg_z (old_invoice_line_id);
  -- OpenUpgrade 13.0 may have given a line the union of its group's taxes; the source's own
  -- invoice line says which were its own. A zero-amount line's taxes weigh nothing.
  IF to_regclass('account_invoice_line_tax') IS NOT NULL THEN
    UPDATE odwg_z z SET tk = coalesce((SELECT string_agg(t.tax_id::text, ',' ORDER BY t.tax_id)
      FROM account_invoice_line_tax t WHERE t.invoice_line_id = z.old_invoice_line_id), '');
  END IF;

  CREATE INDEX ON odwg_z (move_id, account_id, tk);
  ANALYZE odwg_g;
  ANALYZE odwg_z;

  -- The document's direction (a vendor bill and a customer refund debit their lines), and
  -- whether it is in its company's currency.
  CREATE TEMP TABLE odwg_m ON COMMIT DROP AS
    SELECT m.id move_id, m.name,
      CASE WHEN m.move_type IN ('in_invoice', 'out_refund') THEN 1 ELSE -1 END d,
      (m.currency_id = c.currency_id) own_currency
    FROM account_move m JOIN res_company c ON c.id = m.company_id
    WHERE m.id IN (SELECT move_id FROM odwg_g);

  -- A move with a single grouped account whose lines add up to it: the lines take that
  -- account (the source's journal item may have been moved to another account).
  UPDATE odwg_z z SET account_id = s.account_id FROM (
    SELECT g.move_id, min(g.account_id) account_id, sum(g.balance) b FROM odwg_g g GROUP BY 1
    HAVING count(DISTINCT g.account_id) = 1) s
  JOIN (SELECT move_id, sum(price_subtotal) s FROM odwg_z GROUP BY 1) zs USING (move_id)
  WHERE z.move_id = s.move_id AND abs(abs(s.b) - abs(zs.s)) < 0.05;

  -- Groups: one move, one account, one set of taxes.
  CREATE TEMP TABLE odwg_grp ON COMMIT DROP AS
    SELECT move_id, account_id, tk, g.b, g.partners, g.reconcilable, g.settled, z.s, NULL::text reason
    FROM (SELECT gi.move_id, gi.account_id, gi.tk, sum(gi.balance) b,
                 count(DISTINCT coalesce(gi.partner_id, 0)) partners,
                 bool_or(coalesce(a.reconcile, false)) reconcilable, bool_or(gi.settled) settled
          FROM odwg_g gi JOIN account_account a ON a.id = gi.account_id GROUP BY 1, 2, 3) g
    FULL JOIN (SELECT move_id, account_id, tk, sum(price_subtotal) s FROM odwg_z GROUP BY 1, 2, 3) z
      USING (move_id, account_id, tk);
  UPDATE odwg_grp p SET reason = CASE
      WHEN p.b IS NULL THEN CASE WHEN abs(p.s) >= 0.005
        THEN 'invoice lines with no grouped item on their account and taxes' END
      WHEN NOT m.own_currency THEN 'foreign currency'
      WHEN p.settled THEN 'reconciled, partly or fully'
      WHEN p.partners > 1 THEN 'grouped items with different partners'
      WHEN p.s IS NULL THEN 'grouped item with no invoice line on its account and taxes'
      WHEN abs(p.b - m.d * p.s) >= 0.05 THEN 'amounts differ'
    END
  FROM odwg_m m WHERE m.move_id = p.move_id;

  -- A grouped item something else points at (a reconciliation, say) keeps its group.
  FOR fk IN SELECT * FROM odwg_fk WHERE kind = 'other' LOOP
    EXECUTE format(
      'UPDATE odwg_grp p SET reason = %L FROM odwg_g g
        WHERE p.reason IS NULL AND p.b IS NOT NULL AND g.move_id = p.move_id
          AND g.account_id = p.account_id AND g.tk = p.tk
          AND EXISTS (SELECT 1 FROM %I x WHERE x.%I = g.id)',
      'referenced by ' || fk.tbl || '.' || fk.col, fk.tbl, fk.col);
  END LOOP;

  CREATE TEMP TABLE odwg_ok ON COMMIT DROP AS
    SELECT move_id, account_id, tk, b, reconcilable FROM odwg_grp WHERE b IS NOT NULL AND reason IS NULL;
  INSERT INTO odwg_left
    SELECT p.move_id, m.name, p.account_id, p.tk, coalesce(p.b, m.d * p.s), p.reason
    FROM odwg_grp p JOIN odwg_m m USING (move_id) WHERE p.reason IS NOT NULL;
  IF NOT EXISTS (SELECT 1 FROM odwg_ok) THEN
    RAISE NOTICE '[repair] grouped invoice items: no group can be repaired, % left', (SELECT count(*) FROM odwg_left);
    RETURN;
  END IF;
  CREATE INDEX ON odwg_ok (move_id, account_id, tk);
  CREATE TEMP TABLE odwg_moves ON COMMIT DROP AS SELECT DISTINCT move_id FROM odwg_ok;
  CREATE UNIQUE INDEX ON odwg_moves (move_id);
  ANALYZE odwg_ok;
  ANALYZE odwg_moves;
  CREATE TEMP TABLE odwg_main ON COMMIT DROP AS
    SELECT DISTINCT ON (z.move_id, z.account_id, z.tk) z.move_id, z.account_id, z.tk, z.id zid
    FROM odwg_z z JOIN odwg_ok USING (move_id, account_id, tk)
    ORDER BY z.move_id, z.account_id, z.tk, abs(z.price_subtotal) DESC, z.id;
  CREATE INDEX ON odwg_main (move_id, account_id, tk);
  ANALYZE odwg_main;

  -- Before: what the checks compare, on the moves that change only.
  CREATE TEMP TABLE odwg_b_acc ON COMMIT DROP AS
    SELECT move_id, account_id, coalesce(partner_id, 0) partner_id, sum(balance) b,
           sum(coalesce(amount_residual, 0)) r
    FROM account_move_line WHERE move_id IN (SELECT move_id FROM odwg_moves) GROUP BY 1, 2, 3;
  CREATE TEMP TABLE odwg_b_tax ON COMMIT DROP AS
    SELECT l.move_id, r.account_tax_id, sum(l.balance) b
    FROM account_move_line l JOIN account_move_line_account_tax_rel r ON r.account_move_line_id = l.id
    WHERE l.move_id IN (SELECT move_id FROM odwg_moves) GROUP BY 1, 2;
  CREATE TEMP TABLE odwg_b_amt ON COMMIT DROP AS
    SELECT id, amount_untaxed, amount_tax, amount_total, amount_residual
    FROM account_move WHERE id IN (SELECT move_id FROM odwg_moves);
  -- What a record linked to a repaired grouped item adds up to (what a declaration's box shows
  -- when it is drilled into): the item's lines take its links, so it must not change.
  CREATE TEMP TABLE odwg_b_sum (tbl text, other text, s numeric) ON COMMIT DROP;
  FOR fk IN SELECT * FROM odwg_fk WHERE kind = 'link' LOOP
    EXECUTE format(
      'INSERT INTO odwg_b_sum SELECT %L, x.%I::text, sum(l.balance) FROM %I x
        JOIN account_move_line l ON l.id = x.%I
        WHERE x.%I IN (SELECT x2.%I FROM %I x2 JOIN odwg_g g ON g.id = x2.%I
                       JOIN odwg_ok o ON o.move_id = g.move_id AND o.account_id = g.account_id
                                     AND o.tk = g.tk)
        GROUP BY 2',
      fk.tbl, fk.other, fk.tbl, fk.col, fk.other, fk.other, fk.tbl, fk.col);
  END LOOP;
  CREATE TEMP TABLE odwg_b_ref (tbl text, move_id integer, other text, n bigint) ON COMMIT DROP;
  FOR fk IN SELECT * FROM odwg_fk LOOP
    IF fk.kind = 'link' THEN
      EXECUTE format(
        'INSERT INTO odwg_b_ref SELECT DISTINCT %L, l.move_id, x.%I::text, 1 FROM %I x
          JOIN account_move_line l ON l.id = x.%I WHERE l.move_id IN (SELECT move_id FROM odwg_moves)',
        fk.tbl, fk.other, fk.tbl, fk.col);
    ELSE
      EXECUTE format(
        'INSERT INTO odwg_b_ref SELECT %L, l.move_id, NULL, count(*) FROM %I x
          JOIN account_move_line l ON l.id = x.%I WHERE l.move_id IN (SELECT move_id FROM odwg_moves)
          GROUP BY 2',
        fk.tbl, fk.tbl, fk.col);
    END IF;
  END LOOP;

  -- 1. The lines of a repaired group take back their own taxes, then their own amount, with
  -- the group's account and partner.
  IF to_regclass('account_invoice_line_tax') IS NOT NULL THEN
    CREATE TEMP TABLE odwg_retax ON COMMIT DROP AS
      SELECT z.id, z.tk FROM odwg_z z JOIN odwg_ok USING (move_id, account_id, tk) WHERE z.tk <> z.cur_tk;
    DELETE FROM account_move_line_account_tax_rel WHERE account_move_line_id IN (SELECT id FROM odwg_retax);
    INSERT INTO account_move_line_account_tax_rel (account_move_line_id, account_tax_id)
      SELECT t.id, unnest(string_to_array(t.tk, ','))::integer FROM odwg_retax t WHERE t.tk <> '';
    SELECT count(*) INTO restored FROM odwg_retax;
  END IF;
  UPDATE account_move_line l SET account_id = z.account_id,
    partner_id = (SELECT g.partner_id FROM odwg_g g WHERE g.move_id = z.move_id
                  AND g.account_id = z.account_id AND g.tk = z.tk ORDER BY g.id LIMIT 1),
    balance = m.d * z.price_subtotal, amount_currency = m.d * z.price_subtotal,
    debit = greatest(m.d * z.price_subtotal, 0), credit = greatest(-m.d * z.price_subtotal, 0),
    -- On a reconcilable account the amount is open, as the grouped item's was.
    amount_residual = CASE WHEN odwg_ok.reconcilable THEN m.d * z.price_subtotal ELSE l.amount_residual END,
    amount_residual_currency = CASE WHEN odwg_ok.reconcilable THEN m.d * z.price_subtotal
                                    ELSE l.amount_residual_currency END
  FROM odwg_z z JOIN odwg_ok USING (move_id, account_id, tk) JOIN odwg_m m USING (move_id)
  WHERE l.id = z.id;
  GET DIAGNOSTICS moved = ROW_COUNT;
  -- 2. The cents of rounding, to the group's largest line.
  UPDATE account_move_line l
    SET balance = l.balance + dd.d, amount_currency = l.amount_currency + dd.d,
        debit = greatest(l.balance + dd.d, 0), credit = greatest(-(l.balance + dd.d), 0),
        amount_residual = CASE WHEN dd.reconcilable THEN l.amount_residual + dd.d ELSE l.amount_residual END,
        amount_residual_currency = CASE WHEN dd.reconcilable THEN l.amount_residual_currency + dd.d
                                        ELSE l.amount_residual_currency END
  FROM (SELECT mn.zid, o.reconcilable, o.b - t.s d
        FROM odwg_ok o JOIN odwg_main mn USING (move_id, account_id, tk)
        JOIN (SELECT z.move_id, z.account_id, z.tk, sum(l2.balance) s
              FROM odwg_z z JOIN account_move_line l2 ON l2.id = z.id GROUP BY 1, 2, 3) t
          USING (move_id, account_id, tk)) dd
  WHERE l.id = dd.zid AND dd.d <> 0;
  -- 3. What pointed at a grouped item now points at the lines that carry its amount.
  FOR fk IN SELECT * FROM odwg_fk LOOP
    IF fk.kind = 'link' THEN
      EXECUTE format(
        'INSERT INTO %I (%I, %I) SELECT DISTINCT z.id, x.%I FROM %I x
          JOIN odwg_g g ON g.id = x.%I
          JOIN odwg_ok o ON o.move_id = g.move_id AND o.account_id = g.account_id AND o.tk = g.tk
          JOIN odwg_z z ON z.move_id = g.move_id AND z.account_id = g.account_id AND z.tk = g.tk
          WHERE NOT EXISTS (SELECT 1 FROM %I y WHERE y.%I = z.id AND y.%I = x.%I)',
        fk.tbl, fk.col, fk.other, fk.other, fk.tbl, fk.col, fk.tbl, fk.col, fk.other, fk.other);
    ELSE
      EXECUTE format(
        'UPDATE %I x SET %I = mn.zid FROM odwg_g g
          JOIN odwg_main mn USING (move_id, account_id, tk) WHERE x.%I = g.id',
        fk.tbl, fk.col, fk.col);
    END IF;
  END LOOP;
  -- 4. The grouped items go.
  DELETE FROM account_move_line WHERE id IN (
    SELECT g.id FROM odwg_g g JOIN odwg_ok USING (move_id, account_id, tk));
  GET DIAGNOSTICS removed = ROW_COUNT;

  -- Checks: any failure raises, and nothing is kept.
  IF EXISTS (SELECT 1 FROM odwg_b_acc b FULL JOIN (
        SELECT move_id, account_id, coalesce(partner_id, 0) partner_id, sum(balance) b,
               sum(coalesce(amount_residual, 0)) r
        FROM account_move_line WHERE move_id IN (SELECT move_id FROM odwg_moves) GROUP BY 1, 2, 3) a
      USING (move_id, account_id, partner_id)
      WHERE abs(coalesce(a.b, 0) - coalesce(b.b, 0)) >= 0.005) THEN
    RAISE EXCEPTION '[repair] grouped invoice items: check failed: a balance per account and partner changed';
  END IF;
  IF EXISTS (SELECT 1 FROM odwg_b_acc b FULL JOIN (
        SELECT move_id, account_id, coalesce(partner_id, 0) partner_id,
               sum(coalesce(amount_residual, 0)) r
        FROM account_move_line WHERE move_id IN (SELECT move_id FROM odwg_moves) GROUP BY 1, 2, 3) a
      USING (move_id, account_id, partner_id)
      WHERE abs(coalesce(a.r, 0) - coalesce(b.r, 0)) >= 0.005) THEN
    RAISE EXCEPTION '[repair] grouped invoice items: check failed: an amount still open changed';
  END IF;
  IF EXISTS (SELECT 1 FROM account_move_line WHERE move_id IN (SELECT move_id FROM odwg_moves)
      GROUP BY move_id HAVING sum(debit) <> sum(credit) OR abs(sum(balance)) >= 0.005) THEN
    RAISE EXCEPTION '[repair] grouped invoice items: check failed: a move is not balanced';
  END IF;
  IF EXISTS (SELECT 1 FROM odwg_b_tax b FULL JOIN (
        SELECT l.move_id, r.account_tax_id, sum(l.balance) b
        FROM account_move_line l JOIN account_move_line_account_tax_rel r ON r.account_move_line_id = l.id
        WHERE l.move_id IN (SELECT move_id FROM odwg_moves) GROUP BY 1, 2) a
      USING (move_id, account_tax_id)
      WHERE abs(coalesce(a.b, 0) - coalesce(b.b, 0)) >= 0.005) THEN
    RAISE EXCEPTION '[repair] grouped invoice items: check failed: a tax base changed';
  END IF;
  IF EXISTS (SELECT 1 FROM odwg_b_amt b JOIN account_move m USING (id)
      WHERE (b.amount_untaxed, b.amount_tax, b.amount_total, b.amount_residual)
        IS DISTINCT FROM (m.amount_untaxed, m.amount_tax, m.amount_total, m.amount_residual)) THEN
    RAISE EXCEPTION '[repair] grouped invoice items: check failed: an invoice''s amounts changed';
  END IF;
  CREATE TEMP TABLE odwg_a_ref (tbl text, move_id integer, other text, n bigint) ON COMMIT DROP;
  FOR fk IN SELECT * FROM odwg_fk LOOP
    IF fk.kind = 'link' THEN
      EXECUTE format(
        'INSERT INTO odwg_a_ref SELECT DISTINCT %L, l.move_id, x.%I::text, 1 FROM %I x
          JOIN account_move_line l ON l.id = x.%I WHERE l.move_id IN (SELECT move_id FROM odwg_moves)',
        fk.tbl, fk.other, fk.tbl, fk.col);
    ELSE
      EXECUTE format(
        'INSERT INTO odwg_a_ref SELECT %L, l.move_id, NULL, count(*) FROM %I x
          JOIN account_move_line l ON l.id = x.%I WHERE l.move_id IN (SELECT move_id FROM odwg_moves)
          GROUP BY 2',
        fk.tbl, fk.tbl, fk.col);
    END IF;
  END LOOP;
  IF EXISTS (SELECT tbl, move_id, other, n FROM odwg_b_ref
             EXCEPT SELECT tbl, move_id, other, n FROM odwg_a_ref) THEN
    RAISE EXCEPTION '[repair] grouped invoice items: check failed: a link to a grouped item was lost (%)',
      (SELECT string_agg(DISTINCT tbl, ', ') FROM (SELECT tbl, move_id, other, n FROM odwg_b_ref
        EXCEPT SELECT tbl, move_id, other, n FROM odwg_a_ref) lost);
  END IF;

  CREATE TEMP TABLE odwg_a_sum (tbl text, other text, s numeric) ON COMMIT DROP;
  FOR fk IN SELECT * FROM odwg_fk WHERE kind = 'link' LOOP
    EXECUTE format(
      'INSERT INTO odwg_a_sum SELECT %L, x.%I::text, sum(l.balance) FROM %I x
        JOIN account_move_line l ON l.id = x.%I
        WHERE x.%I::text IN (SELECT other FROM odwg_b_sum WHERE tbl = %L)
        GROUP BY 2',
      fk.tbl, fk.other, fk.tbl, fk.col, fk.other, fk.tbl);
  END LOOP;
  IF EXISTS (SELECT 1 FROM odwg_b_sum b LEFT JOIN odwg_a_sum a USING (tbl, other)
             WHERE abs(coalesce(a.s, 0) - b.s) >= 0.005) THEN
    RAISE EXCEPTION '[repair] grouped invoice items: check failed: what a link adds up to changed (%)',
      (SELECT string_agg(DISTINCT b.tbl, ', ') FROM odwg_b_sum b LEFT JOIN odwg_a_sum a USING (tbl, other)
       WHERE abs(coalesce(a.s, 0) - b.s) >= 0.005);
  END IF;

  RAISE NOTICE '[repair] grouped invoice items: % groups repaired on % invoices (% items removed, % lines given their amount, % lines given back their own taxes, % reused zero-amount lines kept as they are), % groups left',
    (SELECT count(*) FROM odwg_ok), (SELECT count(*) FROM odwg_moves), removed, moved, restored, kept,
    (SELECT count(*) FROM odwg_left);
END
$odwg$;
SELECT move_id, move_name, account_id, taxes, amount, reason FROM odwg_left
  ORDER BY move_id, account_id, taxes;
COMMIT;
\\else
\\warn '[repair] grouped invoice items: not applicable (no OpenUpgrade 13.0 invoice columns)'
\\endif
"""
