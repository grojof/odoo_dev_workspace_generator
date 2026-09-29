"""The coherence audit of one database: which checks apply, their SQL, their verdicts.

Pure: builds queries and reads rows; ``workflows.checks`` runs the queries and prints.
Each check decides whether it applies from the tables and columns the database has, so
the same audit reads a source copy, a checkpoint between steps and the migrated
database. It changes nothing: a finding names the fix, it does not apply it.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass

from .intake import (
    BANK_DUPLICATES_SQL,
    BANK_LOCKED_SQL,
    JOURNAL_CODES_SQL,
    journal_code_plan,
    parse_bank_copies,
    parse_locked_lines,
)
from .templates import STALE_RECONCILED_LINES_FROM

#: What a check concluded. Only ``found`` is a finding; ``info`` is worth reading and
#: changes no exit code; ``n/a`` and ``unreadable`` measured nothing.
FOUND, CLEAN, INFO, NOT_APPLICABLE, UNREADABLE = "found", "clean", "info", "n/a", "unreadable"

#: Examples printed per check. Ids, codes and model names only: never a partner or a label.
EXAMPLES = 10

#: The columns the checks depend on. One query reads which of them the database has, from
#: ``pg_attribute``: ``information_schema`` hides what the role may not read, and a check
#: the role cannot read must say so, not pass as not applicable.
_MARKERS = (
    ("account_journal", "code"),
    ("account_journal", "default_debit_account_id"),
    ("account_journal", "suspense_account_id"),
    ("account_bank_statement_line", "id"),
    ("account_bank_statement_line", "move_id"),
    ("account_bank_statement_line", "is_reconciled"),
    ("account_move_line", "statement_line_id"),
    ("account_move_line", "payment_id"),
    ("account_move_line", "amount_residual_currency"),
    ("account_account", "reconcile"),
    ("res_company", "period_lock_date"),
    ("ir_model_constraint", "type"),
    ("ir_model_fields", "required"),
    ("ir_filters", "domain"),
    ("ir_exports_line", "name"),
)

CATALOGUE_SQL = (
    "SELECT c.relname, a.attname FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
    "WHERE c.relnamespace = current_schema()::regnamespace AND c.relkind = 'r' "
    "AND NOT a.attisdropped AND (c.relname::text, a.attname::text) IN ("
    + ", ".join(f"('{table}', '{column}')" for table, column in _MARKERS) + ")"
)

Catalogue = frozenset[tuple[str, str]]


def parse_catalogue(rows: list[list[str]]) -> Catalogue:
    return frozenset((r[0], r[1]) for r in rows if len(r) >= 2)


def is_odoo(catalogue: Catalogue) -> bool:
    return ("ir_model_fields", "required") in catalogue


def legacy_statement_lines(catalogue: Catalogue) -> bool:
    """Up to 13.0: statement lines exist and have no entry of their own."""
    return (("account_bank_statement_line", "id") in catalogue
            and ("account_bank_statement_line", "move_id") not in catalogue
            and ("account_move_line", "statement_line_id") in catalogue)


def applies(check: str, catalogue: Catalogue) -> bool:
    has = catalogue.__contains__
    match check:
        case "journal-codes":
            return has(("account_journal", "code"))
        case "bank-duplicates":
            return legacy_statement_lines(catalogue)
        case "bank-payments":
            return (legacy_statement_lines(catalogue)
                    and has(("account_journal", "default_debit_account_id"))
                    and has(("account_move_line", "payment_id"))
                    and has(("res_company", "period_lock_date")))
        case "bank-closed-lines":
            return legacy_statement_lines(catalogue) and has(("res_company", "period_lock_date"))
        case "constraints-missing":
            return has(("ir_model_constraint", "type"))
        case "required-empty":
            return has(("ir_model_fields", "required"))
        case "statement-lines-reconciled":
            return (has(("account_bank_statement_line", "is_reconciled"))
                    and has(("account_journal", "suspense_account_id"))
                    and has(("account_move_line", "amount_residual_currency"))
                    and has(("account_account", "reconcile")))
        case "saved-field-paths":
            return has(("ir_filters", "domain")) and has(("ir_exports_line", "name"))
    raise ValueError(f"unknown check {check!r}")


#: In the order they are run and printed: the source's problems first, then what the
#: chain can leave behind.
CHECKS = ("journal-codes", "bank-duplicates", "bank-payments", "bank-closed-lines",
          "constraints-missing", "required-empty", "statement-lines-reconciled",
          "saved-field-paths")


@dataclass(frozen=True)
class Result:
    check: str
    verdict: str
    count: int = 0
    examples: tuple[str, ...] = ()
    detail: str = ""
    more: int = 0    # lines not shown among the examples


def _listed(check: str, verdict: str, count: int, lines: list[str], detail: str = "") -> Result:
    return Result(check, verdict, count, tuple(lines[:EXAMPLES]), detail,
                  max(0, len(lines) - EXAMPLES))


# --- journal codes --------------------------------------------------------------------------

def journal_codes_result(rows: list[list[str]]) -> Result:
    """Shared codes are a finding (``unique(company_id, code)`` refuses them from 15.0);
    codes differing only by case or spaces are information."""
    plan, _problems = journal_code_plan(rows)
    groups: dict[tuple[int, str, str], list[int]] = {}
    for j in plan:
        groups.setdefault((j.company, j.group, j.code.strip().upper()), []).append(j.id)
    shared = [k for k in groups if k[1] == "shared"]
    confusable = [k for k in groups if k[1] == "confusable"]
    lines = [f"company {c}: {code} ({kind}, journals {', '.join(map(str, groups[(c, kind, code)]))})"
             for c, kind, code in sorted(shared) + sorted(confusable)]
    if shared:
        detail = f"differing only by case or spaces: {len(confusable)}" if confusable else ""
        return _listed("journal-codes", FOUND, len(shared), lines, detail)
    if confusable:
        return _listed("journal-codes", INFO, len(confusable), lines)
    return Result("journal-codes", CLEAN)


# --- bank lines, sources up to 13.0 -------------------------------------------------------

def bank_duplicates_result(rows: list[list[str]]) -> tuple[Result, set[int]]:
    """The result, and the duplicate line ids (the closed-period count leaves them out)."""
    copies = parse_bank_copies(rows)
    if not copies:
        return Result("bank-duplicates", CLEAN), set()
    twice = sum(1 for c in copies if c.kind != "duplicate")
    lines = [f"line {c.line} (journal {c.journal}, {c.date}, {c.amount}): {c.kind} of {c.kept}"
             for c in copies]
    detail = f"reconciled in more than one copy: {twice}" if twice else ""
    return (_listed("bank-duplicates", FOUND, len(copies), lines, detail),
            {c.line for c in copies})


#: ``line, journal, date, amount, closed``: unreconciled lines (no journal item points at
#: them) matching, by journal and amount, a posted payment line on the journal's bank
#: account that no statement line points at. From 14.0 each would be counted twice.
BANK_PAYMENTS_SQL = """
WITH rec AS (
    SELECT DISTINCT statement_line_id AS id FROM account_move_line
    WHERE statement_line_id IS NOT NULL
), pay AS (
    SELECT DISTINCT aml.journal_id AS j, round(aml.balance, 2) AS amount
    FROM account_move_line aml JOIN account_journal aj ON aj.id = aml.journal_id
    JOIN account_move m ON m.id = aml.move_id AND m.state = 'posted'
    WHERE aml.payment_id IS NOT NULL AND aml.statement_line_id IS NULL
      AND aml.account_id IN (aj.default_debit_account_id, aj.default_credit_account_id)
), lock AS (
    SELECT id, greatest(fiscalyear_lock_date, period_lock_date) AS day FROM res_company
)
SELECT l.id, aj.code, l.date, l.amount, coalesce(l.date <= lock.day, false)
FROM account_bank_statement_line l LEFT JOIN rec ON rec.id = l.id
JOIN account_bank_statement s ON s.id = l.statement_id JOIN lock ON lock.id = s.company_id
JOIN account_journal aj ON aj.id = l.journal_id
JOIN pay ON pay.j = l.journal_id AND pay.amount = round(l.amount, 2)
WHERE rec.id IS NULL ORDER BY l.date, l.id"""


def bank_payments_result(rows: list[list[str]], duplicates: set[int]) -> Result:
    lines = [r for r in rows if len(r) >= 5 and r[0].isdigit() and int(r[0]) not in duplicates]
    if not lines:
        return Result("bank-payments", CLEAN)
    closed = sum(1 for r in lines if r[4] == "t")
    examples = [f"line {r[0]} (journal {r[1]}, {r[2]}, {r[3]}"
                + (", closed period)" if r[4] == "t" else ")") for r in lines]
    return _listed("bank-payments", FOUND, len(lines), examples,
                   f"closed periods: {closed}, open periods: {len(lines) - closed}")


def bank_closed_lines_result(rows: list[list[str]], duplicates: set[int]) -> Result:
    lines = parse_locked_lines(rows, duplicates)
    if not lines:
        return Result("bank-closed-lines", CLEAN)
    kept = sum(1 for x in lines if x.kept)
    examples = [f"line {x.line} (journal {x.journal}, {x.date}, {x.amount})" for x in lines]
    return _listed("bank-closed-lines", INFO, len(lines), examples,
                   f"matching an open receivable or payable: {kept}" if kept else "")


# --- constraints -----------------------------------------------------------------------------

#: ``model, constraint, definition, module``: unique and check constraints of installed
#: modules whose table exists, with no constraint and no index of their (truncated) name.
#: Foreign keys are not read: the table keeps rows for tables long gone.
CONSTRAINTS_MISSING_SQL = r"""
SELECT m.model, c.name,
       regexp_replace(coalesce(c.definition, ''), '[\t\n\r]+', ' ', 'g'), mm.name
FROM ir_model_constraint c JOIN ir_model m ON m.id = c.model
JOIN ir_module_module mm ON mm.id = c.module AND mm.state = 'installed'
WHERE c.type = 'u' AND to_regclass(quote_ident(replace(m.model, '.', '_'))) IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM pg_constraint p WHERE p.conname = left(c.name, 63))
  AND NOT EXISTS (SELECT 1 FROM pg_class i WHERE i.relkind = 'i' AND i.relname = left(c.name, 63))
ORDER BY 1, 2"""


def constraints_result(rows: list[list[str]]) -> Result:
    found = [r for r in rows if len(r) >= 4]
    if not found:
        return Result("constraints-missing", CLEAN)
    lines = [f"{r[0]}: {r[1]} {r[2]} ({r[3]})".replace("  ", " ") for r in found]
    return _listed("constraints-missing", FOUND, len(found), lines)


# --- required fields -------------------------------------------------------------------------

#: ``model, field, table, has column, type, table has active``: stored required fields of
#: non-transient models that can hold no value. A column that is NOT NULL cannot, so only
#: nullable columns are candidates, and binaries, which are mostly attachments.
REQUIRED_CANDIDATES_SQL = """
SELECT f.model, f.name, cl.relname, col.attname IS NOT NULL, f.ttype,
       EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = cl.oid AND a.attname = 'active'
               AND NOT a.attisdropped)
FROM ir_model_fields f JOIN ir_model m ON m.model = f.model AND NOT coalesce(m.transient, false)
JOIN pg_class cl ON cl.relname = replace(f.model, '.', '_') AND cl.relkind = 'r'
                AND cl.relnamespace = current_schema()::regnamespace
LEFT JOIN pg_attribute col ON col.attrelid = cl.oid AND col.attname = f.name
                          AND NOT col.attisdropped
WHERE f.required AND f.store AND f.ttype NOT IN ('one2many', 'many2many')
  AND ((col.attname IS NOT NULL AND NOT col.attnotnull)
       OR (col.attname IS NULL AND f.ttype = 'binary'))
ORDER BY 1, 2"""

_MODEL_RE = re.compile(r"^[a-z_][a-z0-9_.]*$")
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class Candidate:
    model: str
    field: str
    table: str
    has_column: bool
    binary: bool
    has_active: bool


def parse_candidates(rows: list[list[str]]) -> list[Candidate]:
    """The candidates whose names are safe to quote into the counting query; any other is
    dropped rather than risked in SQL."""
    return [Candidate(r[0], r[1], r[2], r[3] == "t", r[4] == "binary", r[5] == "t")
            for r in rows
            if len(r) >= 6 and _MODEL_RE.fullmatch(r[0]) and _IDENT_RE.fullmatch(r[1])
            and _IDENT_RE.fullmatch(r[2])]


def required_counts_sql(candidates: list[Candidate]) -> str | None:
    """``model, field, empty, empty and active``: one branch per candidate. On a table
    without ``active`` every record counts as active."""
    if not candidates:
        return None
    branches = []
    for c in candidates:
        active = 'count(*) FILTER (WHERE t."active")' if c.has_active else "count(*)"
        if c.binary:
            empty = (f"NOT EXISTS (SELECT 1 FROM ir_attachment a WHERE a.res_model = '{c.model}' "
                     f"AND a.res_field = '{c.field}' AND a.res_id = t.id)")
            if c.has_column:
                empty += f' AND t."{c.field}" IS NULL'
        else:
            empty = f't."{c.field}" IS NULL'
        branches.append(f"SELECT '{c.model}', '{c.field}', count(*), {active} "
                        f'FROM "{c.table}" t WHERE {empty}')
    return "\nUNION ALL ".join(branches)


def required_result(rows: list[list[str]]) -> Result:
    counts = [(r[0], r[1], int(r[2]), int(r[3])) for r in rows
              if len(r) >= 4 and r[2].isdigit() and r[3].isdigit() and int(r[2])]
    active = [c for c in counts if c[3]]
    archived = [c for c in counts if not c[3]]
    lines = ([f"{m}.{f}: {n} empty, {a} active" for m, f, n, a in active]
             + [f"{m}.{f}: {n} empty, archived only" for m, f, n, _a in archived])
    if active:
        detail = f"empty on archived records only: {len(archived)}" if archived else ""
        return _listed("required-empty", FOUND, len(active), lines, detail)
    if archived:
        return _listed("required-empty", INFO, len(archived), lines)
    return Result("required-empty", CLEAN)


# --- statement lines, from 14.0 -----------------------------------------------------------

#: ``line, journal, date``: the lines the 14.0 repair recomputes.
STALE_RECONCILED_SQL = (f"SELECT l.id, j.code, m.date {STALE_RECONCILED_LINES_FROM} "
                        "ORDER BY m.date, l.id")


def stale_reconciled_result(rows: list[list[str]]) -> Result:
    lines = [r for r in rows if len(r) >= 3 and r[0].isdigit()]
    if not lines:
        return Result("statement-lines-reconciled", CLEAN)
    examples = [f"line {r[0]} (journal {r[1]}, {r[2]})" for r in lines]
    return _listed("statement-lines-reconciled", FOUND, len(lines), examples)


# --- saved filters and exports -------------------------------------------------------------

#: One JSON array per row, so that no tab or newline a user saved in a domain splits it:
#: every field with its relation, every saved filter, every export column.
SAVED_PATHS_SQL = (
    "SELECT json_build_array('field', model, name, coalesce(relation, ''))::text "
    "FROM ir_model_fields "
    "UNION ALL SELECT json_build_array('filter', f.id, f.model_id, f.domain, f.context, "
    "coalesce(to_jsonb(f) ->> 'sort', ''))::text FROM ir_filters f "
    "UNION ALL SELECT json_build_array('export', e.id, e.resource, l.name)::text "
    "FROM ir_exports_line l JOIN ir_exports e ON e.id = l.export_id"
)

#: The context keys whose values name fields to group by or measure.
_GROUPING_KEYS = ("group_by", "col_group_by", "pivot_row_groupby", "pivot_column_groupby",
                  "pivot_measures", "graph_groupbys", "graph_measure")
#: A domain leaf's operators: what tells a leaf from a value that is a list of three strings.
_OPERATORS = frozenset(("=", "!=", "<>", "<", ">", "<=", ">=", "=?", "=like", "=ilike",
                        "like", "not like", "ilike", "not ilike", "in", "not in",
                        "child_of", "parent_of", "any", "not any"))


def _expression(text: str) -> ast.expr | None:
    """A domain, context or sort as Python parses it. Not evaluated: a saved domain may
    call ``context_today()``, and only the field names matter here."""
    try:
        return ast.parse(text or "[]", mode="eval").body
    except (SyntaxError, ValueError):
        return None


def _string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _leaf_names(node: ast.AST) -> list[str]:
    """A leaf's field, or the leaves of a list of leaves and operators. A leaf's value is
    not looked into: ``["a", "in", "b"]`` there is a value, not a leaf."""
    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    if len(node.elts) == 3:
        name, operator = _string(node.elts[0]), _string(node.elts[1])
        if name is not None and operator in _OPERATORS:
            return [name]
    return [name for element in node.elts for name in _leaf_names(element)]


def domain_paths(text: str) -> list[str] | None:
    """The field paths a domain's leaves name; None when it does not parse."""
    node = _expression(text)
    return None if node is None else _leaf_names(node)


def context_paths(text: str) -> list[str] | None:
    """The fields a context groups, measures or orders by; None when it does not parse."""
    node = _expression(text or "{}")
    if node is None:
        return None
    paths: list[str] = []
    if not isinstance(node, ast.Dict):
        return paths
    for key, value in zip(node.keys, node.values, strict=True):
        name = _string(key) if key is not None else None
        items = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
        if name in _GROUPING_KEYS:
            paths += [s for s in map(_string, items) if s]
        elif name == "orderedBy":
            for item in items:
                if isinstance(item, ast.Dict):
                    paths += [s for k, v in zip(item.keys, item.values, strict=True)
                              if k is not None and _string(k) == "name" and (s := _string(v))]
    return paths


def sort_paths(text: str) -> list[str] | None:
    """The fields a saved sort names (``["name desc", ...]``); None when it does not parse."""
    node = _expression(text)
    if node is None:
        return None
    items = node.elts if isinstance(node, (ast.List, ast.Tuple)) else [node]
    return [s.split()[0] for s in map(_string, items) if s and s.split()]


def broken_segment(fields: dict[str, dict[str, str]], model: str, path: str,
                   separator: str) -> str | None:
    """Where a field path breaks, as ``model.field`` (or ``model x`` when the model is
    gone); None when every segment exists. Group-by suffixes (``:month``), a sort's ``-``,
    ``id`` and an export's ``.id`` are not fields."""
    if model not in fields:
        return f"model {model}"
    for raw in path.split(separator):
        segment = raw.split(":")[0].lstrip("-").strip()
        if segment in ("", "id", ".id") or segment.startswith("__"):
            return None
        if segment not in fields[model]:
            return f"{model}.{segment}"
        model = fields[model][segment]
        if not model:
            return None
        if model not in fields:
            return f"model {model}"
    return None


def saved_paths_result(rows: list[list[str]]) -> Result:
    fields: dict[str, dict[str, str]] = {}
    saved: list[list] = []
    for row in rows:
        try:
            item = json.loads(row[0])
        except (IndexError, ValueError):
            continue
        if item[0] == "field":
            fields.setdefault(item[1], {})[item[2]] = item[3]
        else:
            saved.append(item)
    broken: dict[tuple[str, int, str], list[str]] = {}
    for item in saved:
        kind, rid, model = item[0], int(item[1]), item[2]
        if model not in fields:
            broken[(kind, rid, model)] = [f"model {model} is gone"]
            continue
        if kind == "filter":
            parts = ((domain_paths(item[3]), ".", "domain"),
                     (context_paths(item[4]), ".", "context"),
                     (sort_paths(item[5]), ".", "sort"))
        else:
            parts = (([item[3]], "/", "column"),)
        for paths, separator, where in parts:
            if paths is None:
                broken.setdefault((kind, rid, model), []).append(f"its {where} does not parse")
                continue
            for path in paths:
                if broken_segment(fields, model, path, separator):
                    broken.setdefault((kind, rid, model), []).append(path)
    if not broken:
        return Result("saved-field-paths", CLEAN)
    lines = [f"{kind} {rid} on {model}: {', '.join(dict.fromkeys(paths))}"
             for (kind, rid, model), paths in sorted(broken.items())]
    filters = sum(1 for kind, *_ in broken if kind == "filter")
    return _listed("saved-field-paths", FOUND, len(broken), lines,
                   f"{filters} filters, {len(broken) - filters} exports")


def exit_code(results: list[Result]) -> int:
    """1 when a check found something, else 2 when one could not be read, else 0."""
    if any(r.verdict == FOUND for r in results):
        return 1
    if any(r.verdict == UNREADABLE for r in results):
        return 2
    return 0


#: Each check's query. ``required-empty`` is the first of its two passes.
QUERIES = {
    "journal-codes": JOURNAL_CODES_SQL,
    "bank-duplicates": BANK_DUPLICATES_SQL,
    "bank-payments": BANK_PAYMENTS_SQL,
    "bank-closed-lines": BANK_LOCKED_SQL,
    "constraints-missing": CONSTRAINTS_MISSING_SQL,
    "required-empty": REQUIRED_CANDIDATES_SQL,
    "statement-lines-reconciled": STALE_RECONCILED_SQL,
    "saved-field-paths": SAVED_PATHS_SQL,
}
