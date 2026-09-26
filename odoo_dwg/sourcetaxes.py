"""The source's journal-item taxes, kept so that the 13.0 step's additions can be taken back.

OpenUpgrade 13.0 (``account`` 13.0.1.1, ``migration_invoice_moves``) reuses the journal items
a 12.0 invoice had posted as its invoice lines, then gives every reused item its invoice
line's taxes with ``INSERT … ON CONFLICT DO NOTHING``: it adds them to the taxes the item
already bore and takes none away. An item grouped in the source, or a payable line matched
by the relaxed criteria, then bears two sets, and its amount counts in the base of every
tax it bears.

What the item bore exists only in the source. The driver copies it right after restoring
the source dump, and right after the 13.0 step takes back, from each reused item, every
tax it did not bear there and its invoice line did.

Pure: this module holds SQL; the migration driver runs it with ``psql``.
"""

from __future__ import annotations

#: The source up to which OpenUpgrade 13.0 builds invoice lines from journal items.
SOURCE_MAX_MAJOR = 12
#: The step after which the added taxes are taken back, while tax ids are still the source's.
REPAIR_STEP = "13.0"

KEPT_TABLE = "odwg_source_move_line_tax"
MAX_ID_TABLE = "odwg_source_move_line_max"


def applies(source_major: int) -> bool:
    return source_major <= SOURCE_MAX_MAJOR


def keep_sql() -> str:
    """Run on the restored source, before its checkpoint: its journal items' taxes and its
    highest journal-item id, in tables of the tool's own."""
    return f"""\
DO $odwg$
BEGIN
  DROP TABLE IF EXISTS {KEPT_TABLE}, {MAX_ID_TABLE};
  IF to_regclass('account_move_line_account_tax_rel') IS NULL THEN
    RAISE NOTICE '[keep] journal-item taxes: the source has none to keep';
    RETURN;
  END IF;
  CREATE TABLE {KEPT_TABLE} AS
    SELECT account_move_line_id, account_tax_id FROM account_move_line_account_tax_rel;
  CREATE TABLE {MAX_ID_TABLE} AS SELECT coalesce(max(id), 0) AS id FROM account_move_line;
  RAISE NOTICE '[keep] journal-item taxes of the source: % kept',
    (SELECT count(*) FROM {KEPT_TABLE});
END
$odwg$;
"""


def take_back_sql() -> str:
    """Run after the 13.0 step, for ``psql -X -q -At -v ON_ERROR_STOP=1 -f``.

    Progress goes to stderr. Each tax taken back, one per row (journal item, move id, move,
    tax id, amount), goes to stdout."""
    return f"""\
\\set ON_ERROR_STOP 1
SELECT to_regclass('{KEPT_TABLE}') IS NOT NULL AND to_regclass('{MAX_ID_TABLE}') IS NOT NULL
   AND to_regclass('account_invoice_line_tax') IS NOT NULL
   AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema()
               AND table_name = 'account_move_line' AND column_name = 'old_invoice_line_id')
   AS odwg_ready \\gset
\\if :odwg_ready
BEGIN;
-- A reused item existed in the source and OpenUpgrade linked it to an invoice line. What
-- 13.0 added to it: a tax it did not bear in the source, borne by its invoice line.
CREATE TEMP TABLE odwg_added ON COMMIT DROP AS
  SELECT r.account_move_line_id, r.account_tax_id
  FROM account_move_line_account_tax_rel r
  JOIN account_move_line l ON l.id = r.account_move_line_id
  WHERE l.id <= (SELECT id FROM {MAX_ID_TABLE}) AND l.old_invoice_line_id IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM {KEPT_TABLE} k
                    WHERE k.account_move_line_id = l.id AND k.account_tax_id = r.account_tax_id)
    AND EXISTS (SELECT 1 FROM account_invoice_line_tax t
                WHERE t.invoice_line_id = l.old_invoice_line_id AND t.tax_id = r.account_tax_id);
SELECT a.account_move_line_id, l.move_id, m.name, a.account_tax_id, l.balance
  FROM odwg_added a JOIN account_move_line l ON l.id = a.account_move_line_id
  JOIN account_move m ON m.id = l.move_id
  ORDER BY l.move_id, a.account_move_line_id, a.account_tax_id;
DO $odwg$
BEGIN
  RAISE NOTICE '[repair] taxes OpenUpgrade 13.0 added to reused journal items: % taken back from % items',
    (SELECT count(*) FROM odwg_added), (SELECT count(DISTINCT account_move_line_id) FROM odwg_added);
END
$odwg$;
DELETE FROM account_move_line_account_tax_rel r USING odwg_added a
  WHERE r.account_move_line_id = a.account_move_line_id AND r.account_tax_id = a.account_tax_id;
DROP TABLE {KEPT_TABLE}, {MAX_ID_TABLE};
COMMIT;
\\else
\\warn '[repair] taxes OpenUpgrade 13.0 added to reused journal items: SKIPPED - the source checkpoint does not keep the source''s journal-item taxes; only a run from the source dump can repair them'
\\endif
"""
