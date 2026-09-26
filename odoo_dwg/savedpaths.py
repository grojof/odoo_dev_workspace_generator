"""Saved filters and exports whose fields the chain renamed, rewritten at the target step.

Saved filters (``ir.filters``) and export lists (``ir.exports.line``) cross the chain as records,
but the field names inside them are not rewritten when Odoo rebuilds a model (``account.invoice``
became ``account.move``) or when a renamed field sits inside a path: OpenUpgrade's
``rename_fields`` only rewrites a field named directly on the filter's or export's model. Odoo
then fails on them when a user opens them. ``migrate audit`` finds them (check
``saved-field-paths``); this rewrites those whose field has a successor proven from the sources,
through :data:`RENAMES`, and lists the rest.

A path is followed segment by segment through the target's relations, as the audit reads it:
- a renamed segment takes its successor's name;
- a successor that is not relational ends the path there (``user_type_id/display_name`` becomes
  ``account_type``);
- a field with no successor drops an export column and leaves a filter as it is, listed.

A filter is rewritten whole or not at all: one leaf, grouping or sort it cannot rewrite leaves
it untouched and listed. An export's columns that end up the same are kept once.

Stdlib only, and the driver embeds this file verbatim: it runs inside the target's
``odoo-bin shell``, which reads the fields, filters and exports and writes the changes
(:data:`APPLY`).
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass

# The kinds of successor.
RENAME, DROP, EITHER, RANK, INVOICE_LINE = "rename", "drop", "either", "rank", "invoice-line"
#: The move types an Odoo 12 ``account.invoice`` could have.
INVOICE_TYPES = ["out_invoice", "out_refund", "in_invoice", "in_refund"]
_NEGATIVE = frozenset(("!=", "<>", "not like", "not ilike", "not in", "not any"))


@dataclass(frozen=True)
class Successor:
    kind: str
    new: tuple[str, ...] = ()
    values: tuple[tuple[object, object], ...] = ()   # a domain value's own successor


def _rename(new: str, **values: str) -> Successor:
    return Successor(RENAME, (new,), tuple(values.items()))


#: ``(model in the target, old field) -> successor``, each with where the data went.
RENAMES: dict[tuple[str, str], Successor] = {
    # OpenUpgrade 13.0 account/13.0.1.1/post-migration.py fills account.move from
    # account.invoice: name <- COALESCE(number, move_name), invoice_date <- date_invoice,
    # invoice_date_due <- date_due, invoice_origin <- origin, ref <- reference (vendor
    # documents), invoice_payment_ref <- reference (customer documents; 14.0 renames it
    # payment_reference), amount_total_signed <- COALESCE(amount_total_company_signed, ...),
    # amount_residual_signed <- COALESCE(residual_company_signed, residual_signed). Signed
    # amounts follow 13.0's accounting sign: vendor documents are negative.
    ("account.move", "number"): _rename("name"),
    ("account.move", "date_invoice"): _rename("invoice_date"),
    ("account.move", "date_due"): _rename("invoice_date_due"),
    ("account.move", "origin"): _rename("invoice_origin"),
    ("account.move", "reference"): Successor(EITHER, ("ref", "payment_reference")),
    ("account.move", "amount_total_company_signed"): _rename("amount_total_signed"),
    ("account.move", "residual_company_signed"): _rename("amount_residual_signed"),
    ("account.move", "residual_signed"): _rename("amount_residual_signed"),
    # 12.0 account_invoice.py: "Untaxed Amount in Invoice Currency", signed; 18.0
    # account_move.py: amount_untaxed_in_currency_signed, the same in the document's currency.
    ("account.move", "amount_untaxed_invoice_signed"): _rename("amount_untaxed_in_currency_signed"),
    # OCA l10n_es_account_invoice_sequence 12.0: the fiscal number, which OpenUpgrade 13.0
    # carries through number into name.
    ("account.move", "invoice_number"): _rename("name"),
    # OCA account_due_list 12.0 stored_invoice_id: the invoice whose entry is the line's entry.
    # From 13.0 the entry is the invoice.
    ("account.move.line", "stored_invoice_id"): Successor(INVOICE_LINE, ("move_id",)),
    # OpenUpgrade 16.0 analytic: a line's account becomes its distribution.
    ("account.move.line", "analytic_account_id"): _rename("distribution_analytic_account_ids"),
    ("account.move.line", "analytic_tag_ids"): Successor(DROP),
    # OpenUpgrade 13.0 account post-migration fill_res_partner_ranks: rank = posted documents
    # of that side, or 1 when the flag was set.
    ("res.partner", "customer"): Successor(RANK, ("customer_rank",)),
    ("res.partner", "supplier"): Successor(RANK, ("supplier_rank",)),
    # 12.0 account partner.py: the count of the partner's analytic accounts; 18.0 has none.
    ("res.partner", "contracts_count"): Successor(DROP),
    # OpenUpgrade 14.0 account post-migration fill_default_account_id_field.
    ("account.journal", "default_debit_account_id"): _rename("default_account_id"),
    ("account.journal", "default_credit_account_id"): _rename("default_account_id"),
    # OpenUpgrade 16.0 account pre-migration _fill_account_account_type: each account type
    # becomes an account_type value; receivable, payable and liquidity one to one.
    ("account.account", "user_type_id"): _rename("account_type"),
    ("account.account", "internal_type"): _rename(
        "account_type", receivable="asset_receivable", payable="liability_payable",
        liquidity="asset_cash"),
    # OpenUpgrade 16.0 stock pre-migration renames move_lines; 17.0 renames quantity_done and
    # qty_done to quantity (the done quantity of a done move).
    ("stock.picking", "move_lines"): _rename("move_ids"),
    ("stock.move", "quantity_done"): _rename("quantity"),
    ("stock.move.line", "qty_done"): _rename("quantity"),
    # 12.0 stock_account product.py: without a date, qty_at_date is the company-owned
    # qty_available.
    ("product.product", "qty_at_date"): _rename("qty_available"),
    # 12.0 product_template.py: lst_price is related to list_price; price is computed from a
    # pricelist in the context, 0 without one.
    ("product.template", "lst_price"): _rename("list_price"),
    ("product.template", "price"): Successor(DROP),
    # OCA l10n_es_aeat_sii_oca 14.0.2.2.0 pre-migration: tax_agency_id <- sii_tax_agency_id.
    ("res.company", "sii_tax_agency_id"): _rename("tax_agency_id"),
}

Fields = dict[str, dict[str, str]]   # model -> field -> relation ('' when not relational)


def applies(source_major: int, target_major: int) -> bool:
    """Every successor here replaces a field of 12.0 or earlier, from 13.0 on."""
    return source_major <= 12 < target_major


def _successor(fields: Fields, model: str, name: str) -> Successor | None:
    """The successor of a field the target lacks, when the target has every field it names."""
    found = RENAMES.get((model, name))
    if found is None or name in fields.get(model, {}):
        return None
    if all(new in fields.get(model, {}) for new in found.new):
        return found
    return None


def rewrite_path(fields: Fields, model: str, path: str, separator: str) -> str | None:
    """The path with its renamed segments' successors; None when a segment has none (a
    dropped field). Unknown segments and what follows them are kept as they are. A field whose
    successor is a condition, not a field (a reference split in two, an invoice line), raises
    :class:`_Stuck`: a path cannot name it."""
    out: list[str] = []
    segments = path.split(separator)
    for index, raw in enumerate(segments):
        name, colon, suffix = raw.partition(":")
        sign = "-" if name.startswith("-") else ""
        name = name.lstrip("-")
        if name in ("", "id", ".id") or name.startswith("__"):
            out += segments[index:]
            break
        found = _successor(fields, model, name)
        if found is not None:
            if found.kind == DROP:
                return None
            if found.kind in (EITHER, INVOICE_LINE):
                raise _Stuck(name)
            name = found.new[0]
        out.append(f"{sign}{name}{colon}{suffix}")
        relation = fields.get(model, {}).get(name)
        if not relation:
            if found is None:
                out += segments[index + 1:]
            break
        model = relation
    return separator.join(out)


def _parse(text: str, empty: str) -> ast.expr | None:
    try:
        return ast.parse(text or empty, mode="eval").body
    except (SyntaxError, ValueError):
        return None


def _const(node: ast.AST) -> object:
    return node.value if isinstance(node, ast.Constant) else node


def _leaf(name: str, operator: str, value: ast.expr) -> ast.expr:
    return ast.Tuple([ast.Constant(name), ast.Constant(operator), value], ast.Load())


class _Stuck(Exception):
    """A leaf, grouping or sort that cannot be rewritten: the filter is left as it is."""


def _rewrite_leaf(fields: Fields, model: str, node: ast.Tuple | ast.List) -> list[ast.expr]:
    """A leaf, its path's segments renamed. The last segment's successor also decides the
    value (a value map) or the condition (a reference split in two, a rank, an invoice line)."""
    name, operator = str(_const(node.elts[0])), str(_const(node.elts[1]))
    value = node.elts[2]
    segments = name.split(".")
    prefix: list[str] = []
    for index, segment in enumerate(segments[:-1]):
        renamed = rewrite_path(fields, model, segment, ".")
        if renamed is None:
            raise _Stuck(name)
        prefix.append(renamed)
        relation = fields.get(model, {}).get(renamed)
        if not relation:  # unknown here, or not relational: the rest is kept as it is
            path = ".".join(prefix + segments[index + 1:])
            return [node] if path == name else [_leaf(path, operator, value)]
        model = relation
    last = segments[-1]

    def at(field: str) -> str:
        return ".".join(prefix + [field])

    found = _successor(fields, model, last)
    if found is None:
        path = at(last)
        return [node] if path == name else [_leaf(path, operator, value)]
    if found.kind == RENAME:
        mapping = dict(found.values)
        if mapping:
            raw = _const(value)
            if not isinstance(raw, str) or raw not in mapping:
                raise _Stuck(f"{name} {raw!r}")
            value = ast.Constant(mapping[raw])
        return [_leaf(at(found.new[0]), operator, value)]
    if found.kind == EITHER:
        joint = "&" if operator in _NEGATIVE else "|"
        return [ast.Constant(joint)] + [_leaf(at(new), operator, value) for new in found.new]
    if found.kind == RANK and operator in ("=", "!=", "<>"):
        falsy = _const(value) in (False, 0, None)
        truthy = (operator == "=") != falsy
        return [_leaf(at(found.new[0]), ">" if truthy else "=", ast.Constant(0))]
    if found.kind == INVOICE_LINE and operator in ("=", "!=", "<>") and _const(value) is False:
        types = ast.List([ast.Constant(t) for t in INVOICE_TYPES], ast.Load())
        return [_leaf(at("move_id.move_type"), "not in" if operator == "=" else "in", types)]
    raise _Stuck(name)


def _rewrite_domain(fields: Fields, model: str, node: ast.expr) -> ast.expr:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return node
    if len(node.elts) == 3 and isinstance(_const(node.elts[0]), str) \
            and isinstance(_const(node.elts[1]), str) and _const(node.elts[1]) not in ("&", "|"):
        replaced = _rewrite_leaf(fields, model, node)
        if len(replaced) == 1:
            return replaced[0]
        raise _Split(replaced)
    elements: list[ast.expr] = []
    for element in node.elts:
        try:
            elements.append(_rewrite_domain(fields, model, element))
        except _Split as split:
            elements += split.parts
    return type(node)(elements, ast.Load())


class _Split(Exception):
    """A leaf that became an operator and two leaves, spliced into its parent list."""

    def __init__(self, parts: list[ast.expr]) -> None:
        super().__init__()
        self.parts = parts


def _grouping_name(fields: Fields, model: str, raw: str) -> str:
    """A group-by or sort name rewritten; a field whose successor is a condition (an invoice
    line) groups by the successor's field."""
    name, colon, suffix = raw.partition(":")
    found = _successor(fields, model, name.lstrip("-"))
    if found is not None and found.kind in (INVOICE_LINE, RANK):
        sign = "-" if name.startswith("-") else ""
        return f"{sign}{found.new[0]}{colon}{suffix}"
    new = rewrite_path(fields, model, raw, ".")
    if new is None:
        raise _Stuck(raw)
    return new


_GROUPING_KEYS = ("group_by", "col_group_by", "pivot_row_groupby", "pivot_column_groupby",
                  "pivot_measures", "graph_groupbys", "graph_measure")


def _rewrite_context(fields: Fields, model: str, node: ast.expr) -> ast.expr:
    if not isinstance(node, ast.Dict):
        return node
    for key, value in zip(node.keys, node.values, strict=True):
        name = _const(key) if key is not None else None
        items = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
        if name in _GROUPING_KEYS:
            for item in items:
                if isinstance(_const(item), str):
                    item.value = _grouping_name(fields, model, item.value)
        elif name == "orderedBy":
            for item in items:
                if isinstance(item, ast.Dict):
                    for k, v in zip(item.keys, item.values, strict=True):
                        if k is not None and _const(k) == "name" and isinstance(_const(v), str):
                            v.value = _grouping_name(fields, model, v.value)
    return node


def _rewrite_sort(fields: Fields, model: str, node: ast.expr) -> ast.expr:
    items = node.elts if isinstance(node, (ast.List, ast.Tuple)) else [node]
    for item in items:
        if isinstance(_const(item), str) and item.value.split():
            first, _space, rest = item.value.partition(" ")
            item.value = " ".join(filter(None, (_grouping_name(fields, model, first), rest)))
    return node


@dataclass(frozen=True)
class FilterResult:
    domain: str
    context: str
    sort: str
    changed: bool
    stuck: str = ""


def rewrite_filter(fields: Fields, model: str, domain: str, context: str,
                   sort: str) -> FilterResult:
    """A filter's domain, context and sort rewritten, or why it is left as it is."""
    parsed = [_parse(domain, "[]"), _parse(context, "{}"), _parse(sort, "[]")]
    if any(node is None for node in parsed):
        return FilterResult(domain, context, sort, False, "does not parse")
    try:
        new = [_rewrite_domain(fields, model, parsed[0]),
               _rewrite_context(fields, model, parsed[1]),
               _rewrite_sort(fields, model, parsed[2])]
    except _Stuck as stuck:
        return FilterResult(domain, context, sort, False, f"no successor for {stuck}")
    except _Split as split:  # a top-level single leaf that became three elements
        new = [ast.List(split.parts, ast.Load()), parsed[1], parsed[2]]
    texts = [ast.unparse(node) for node in new]
    originals = [ast.unparse(node) for node in
                 (_parse(domain, "[]"), _parse(context, "{}"), _parse(sort, "[]"))]
    if texts == originals:
        return FilterResult(domain, context, sort, False)
    # Odoo checks that a filter's sort is a JSON array (ir_filters check_sort_json).
    return FilterResult(texts[0], texts[1], json.dumps(ast.literal_eval(texts[2])), True)


def rewrite_export(fields: Fields, model: str, lines: list[tuple[int, str]]
                   ) -> list[tuple[int, str | None]]:
    """``(line id, new name)`` for each line that changes: None drops it (no successor, or
    the same column as an earlier line). A column no field can replace is kept as it is."""
    seen: set[str] = set()
    changes: list[tuple[int, str | None]] = []
    for line_id, name in sorted(lines):
        try:
            new = rewrite_path(fields, model, name, "/")
        except _Stuck:
            seen.add(name)
            continue
        if new is None or new in seen:
            changes.append((line_id, None))
            continue
        seen.add(new)
        if new != name:
            changes.append((line_id, new))
    return changes


#: Run by the target's ``odoo-bin shell`` after this file. Appends
#: ``kind<TAB>id<TAB>model<TAB>detail`` to ``$ODWG_SAVED_PATHS_LIST``.
APPLY = r'''
import os
cr = env.cr
cr.execute("SELECT model, name, coalesce(relation, '') FROM ir_model_fields")
fields = {}
for model, name, relation in cr.fetchall():
    fields.setdefault(model, {})[name] = relation
listed = []
cr.execute("SELECT id, model_id, domain, context, coalesce(sort, '[]') FROM ir_filters")
for fid, model, domain, context, sort in cr.fetchall():
    if model not in fields:
        listed.append(("filter-left", fid, model, "model %s is gone" % model))
        continue
    result = rewrite_filter(fields, model, domain, context, sort)
    if result.stuck:
        listed.append(("filter-left", fid, model, result.stuck))
    elif result.changed:
        cr.execute("UPDATE ir_filters SET domain = %s, context = %s, sort = %s WHERE id = %s",
                   [result.domain, result.context, result.sort, fid])
        listed.append(("filter", fid, model, result.domain + " | " + result.context
                       + " | " + result.sort))
cr.execute("SELECT e.id, e.resource, l.id, l.name FROM ir_exports_line l "
           "JOIN ir_exports e ON e.id = l.export_id ORDER BY e.id, l.id")
exports = {}
for eid, model, lid, name in cr.fetchall():
    exports.setdefault((eid, model), []).append((lid, name))
for (eid, model), lines in exports.items():
    if model not in fields:
        listed.append(("export-left", eid, model, "model %s is gone" % model))
        continue
    names = dict(lines)
    for lid, new in rewrite_export(fields, model, lines):
        if new is None:
            cr.execute("DELETE FROM ir_exports_line WHERE id = %s", [lid])
            listed.append(("export-column-dropped", eid, model, names[lid]))
        else:
            cr.execute("UPDATE ir_exports_line SET name = %s WHERE id = %s", [new, lid])
            listed.append(("export-column", eid, model, "%s -> %s" % (names[lid], new)))
with open(os.environ["ODWG_SAVED_PATHS_LIST"], "a", encoding="utf-8") as out:
    for kind, rid, model, detail in listed:
        out.write("%s\t%s\t%s\t%s\n" % (kind, rid, model, detail.replace("\t", " ")))
cr.commit()
counts = {}
for kind, *_ in listed:
    counts[kind] = counts.get(kind, 0) + 1
print("[repair] saved filters and exports: %s" % (", ".join(
    "%s %d" % item for item in sorted(counts.items())) or "nothing to rewrite"))
'''
