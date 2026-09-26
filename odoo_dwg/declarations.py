"""Filed tax declarations, kept whole through the chain.

The OCA AEAT modules store each declaration's boxes in ``l10n_es_aeat_tax_line``, linked to
the journal items that make them up. Each box points at the map line it was computed with,
and that foreign key cascades on delete. When a later version of a declaration's module stops
shipping an old map (OCA dropped the 303 map of July 2021 to 2022 in 17.0, and one of its
boxes in 13.0), Odoo deletes the map's records at the module update, and every filed
declaration of those periods silently loses its boxes: the returns an auditor would open.

The driver copies, right after restoring the source dump, every stored box, its links to
journal items, and the map lines and maps the boxes point at. At the target it puts back
whatever the chain deleted, with the same ids, and checks that every box is there with its
amount. It runs before the grouped-items repair, so that repair moves the boxes' links too.

Pure: this module holds SQL; the migration driver runs it with ``psql``.
"""

from __future__ import annotations

#: Source table -> the tool's copy, in the order they are put back (parents first).
KEPT = (
    ("l10n_es_aeat_map_tax", "odwg_kept_aeat_map_tax"),
    ("l10n_es_aeat_map_tax_line", "odwg_kept_aeat_map_tax_line"),
    ("l10n_es_aeat_tax_line", "odwg_kept_aeat_tax_line"),
)
LINK_TABLE = "account_move_line_l10n_es_aeat_tax_line_rel"
KEPT_LINKS = "odwg_kept_aeat_tax_line_rel"


def keep_sql() -> str:
    """Run on the restored source: its declarations' boxes, their links, and the map lines and
    maps they point at, in tables of the tool's own."""
    drops = ", ".join([kept for _, kept in KEPT] + [KEPT_LINKS])
    return f"""\
DO $odwg$
BEGIN
  DROP TABLE IF EXISTS {drops};
  IF to_regclass('l10n_es_aeat_tax_line') IS NULL THEN
    RAISE NOTICE '[keep] filed declarations: the source has none';
    RETURN;
  END IF;
  CREATE TABLE odwg_kept_aeat_tax_line AS SELECT * FROM l10n_es_aeat_tax_line;
  CREATE TABLE odwg_kept_aeat_map_tax_line AS SELECT * FROM l10n_es_aeat_map_tax_line
    WHERE id IN (SELECT map_line_id FROM odwg_kept_aeat_tax_line);
  CREATE TABLE odwg_kept_aeat_map_tax AS SELECT * FROM l10n_es_aeat_map_tax
    WHERE id IN (SELECT map_parent_id FROM odwg_kept_aeat_map_tax_line);
  IF to_regclass('{LINK_TABLE}') IS NOT NULL THEN
    CREATE TABLE {KEPT_LINKS} AS SELECT l10n_es_aeat_tax_line_id, account_move_line_id
      FROM {LINK_TABLE};
  ELSE
    CREATE TABLE {KEPT_LINKS} (l10n_es_aeat_tax_line_id integer, account_move_line_id integer);
  END IF;
  RAISE NOTICE '[keep] filed declarations of the source: % boxes, % links to journal items',
    (SELECT count(*) FROM odwg_kept_aeat_tax_line), (SELECT count(*) FROM {KEPT_LINKS});
END
$odwg$;
"""


def restore_sql() -> str:
    """Run at the target, for ``psql -X -q -At -v ON_ERROR_STOP=1 -f``.

    Progress goes to stderr. Each box put back, one per row (box id, declaration model,
    declaration id, box number, amount), goes to stdout."""
    pairs = ", ".join(f"('{table}', '{kept}')" for table, kept in KEPT)
    drops = ", ".join([kept for _, kept in KEPT] + [KEPT_LINKS])
    return f"""\
\\set ON_ERROR_STOP 1
SELECT to_regclass('odwg_kept_aeat_tax_line') IS NOT NULL AND to_regclass('{KEPT_LINKS}') IS NOT NULL
   AND to_regclass('l10n_es_aeat_tax_line') IS NOT NULL AS odwg_ready \\gset
\\if :odwg_ready
BEGIN;
CREATE TEMP TABLE odwg_put_back (id integer) ON COMMIT DROP;
DO $odwg$
DECLARE
  t record;
  cols text;
  exprs text;
  n integer;
  maps integer := 0;
  links integer;
  gone integer;
BEGIN
  INSERT INTO odwg_put_back SELECT k.id FROM odwg_kept_aeat_tax_line k
    WHERE NOT EXISTS (SELECT 1 FROM l10n_es_aeat_tax_line x WHERE x.id = k.id);
  -- Whatever the chain deleted goes back with its own id, parents first. Each column the
  -- target still has is cast to the target's type; a text that became translatable goes
  -- in as its English value.
  FOR t IN SELECT * FROM (VALUES {pairs}) v(tbl, kept) LOOP
    SELECT string_agg(format('%I', a.attname), ', ' ORDER BY a.attnum),
           string_agg(CASE WHEN format_type(a.atttypid, a.atttypmod) = 'jsonb'
                            AND format_type(k.atttypid, k.atttypmod) <> 'jsonb'
                           THEN format('jsonb_build_object(''en_US'', k.%I)', a.attname)
                           ELSE format('k.%I::%s', a.attname, format_type(a.atttypid, a.atttypmod))
                      END, ', ' ORDER BY a.attnum)
      INTO cols, exprs
      FROM pg_attribute a
      JOIN pg_attribute k ON k.attrelid = t.kept::regclass AND k.attname = a.attname
                         AND k.attnum > 0 AND NOT k.attisdropped
      WHERE a.attrelid = t.tbl::regclass AND a.attnum > 0 AND NOT a.attisdropped;
    EXECUTE format('INSERT INTO %I (%s) SELECT %s FROM %I k
                    WHERE NOT EXISTS (SELECT 1 FROM %I x WHERE x.id = k.id)',
                   t.tbl, cols, exprs, t.kept, t.tbl);
    GET DIAGNOSTICS n = ROW_COUNT;
    IF t.tbl <> 'l10n_es_aeat_tax_line' THEN
      maps := maps + n;
    END IF;
  END LOOP;

  -- The boxes' links to journal items that still exist.
  IF to_regclass('{LINK_TABLE}') IS NOT NULL THEN
    INSERT INTO {LINK_TABLE} (l10n_es_aeat_tax_line_id, account_move_line_id)
      SELECT DISTINCT k.l10n_es_aeat_tax_line_id, k.account_move_line_id FROM {KEPT_LINKS} k
      WHERE EXISTS (SELECT 1 FROM account_move_line l WHERE l.id = k.account_move_line_id)
        AND NOT EXISTS (SELECT 1 FROM {LINK_TABLE} x
                        WHERE x.l10n_es_aeat_tax_line_id = k.l10n_es_aeat_tax_line_id
                          AND x.account_move_line_id = k.account_move_line_id);
    GET DIAGNOSTICS links = ROW_COUNT;
  END IF;
  SELECT count(*) INTO gone FROM {KEPT_LINKS} k
    WHERE NOT EXISTS (SELECT 1 FROM account_move_line l WHERE l.id = k.account_move_line_id);

  -- Every box the source held is there, with the amount it was filed with.
  IF EXISTS (SELECT 1 FROM odwg_kept_aeat_tax_line k LEFT JOIN l10n_es_aeat_tax_line x USING (id)
             WHERE x.id IS NULL OR x.amount IS DISTINCT FROM k.amount
                OR x.field_number IS DISTINCT FROM k.field_number OR x.res_id IS DISTINCT FROM k.res_id) THEN
    RAISE EXCEPTION '[repair] filed declarations: check failed: a box the source held is missing or changed';
  END IF;
  RAISE NOTICE '[repair] filed declarations: % boxes put back (% maps and map lines), % links put back, % links to journal items the chain no longer has',
    (SELECT count(*) FROM odwg_put_back), maps, coalesce(links, 0), gone;
END
$odwg$;
SELECT x.id, x.model, x.res_id, x.field_number, x.amount FROM l10n_es_aeat_tax_line x
  WHERE x.id IN (SELECT id FROM odwg_put_back) ORDER BY x.model, x.res_id, x.field_number;
DROP TABLE {drops};
COMMIT;
\\else
\\warn '[repair] filed declarations: SKIPPED - the source checkpoint does not keep the source''s declarations; only a run from the source dump can check them'
\\endif
"""
