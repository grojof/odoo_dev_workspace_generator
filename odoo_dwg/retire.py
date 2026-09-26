"""What an uninstall removed, named: the rehearsal's rules and the driver's guard.

The intake rehearses uninstalling modules on a throwaway clone and names every difference
it made. The migration driver uninstalls the modules decided ``dropped`` before the chain on
the copy that enters it, and checks that real uninstall against the same rules: what kinds
of rows may go, and which losses the operator accepted by name after reading the rehearsal.

Standard library only: the driver embeds this file verbatim and runs it with ``python3``,
as it does ``carry.py``. The driver's entry is :func:`main`; the SQL it runs comes from here.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass

#: Exact row counts of every table: the statistics estimate is refreshed by
#: ANALYZE, not by the deletes an uninstall makes. One statement, so no table
#: name ever reaches the shell.
ROWS_SQL = (
    "SELECT c.relname, (xpath('/row/n/text()', query_to_xml(format("
    "'SELECT count(*) AS n FROM public.%I', c.relname), false, true, '')))[1]::text "
    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 1"
)
COLUMNS_SQL = (
    "SELECT c.relname, a.attname FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' "
    "AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped ORDER BY 1, 2"
)
INSTALLED_SQL = (
    "SELECT name FROM ir_module_module WHERE state IN ('installed', 'to upgrade', 'to remove') "
    "ORDER BY 1"
)
#: ``module<TAB>dependency`` for every installed module: an uninstall takes along whatever
#: depends on what it removes.
DEPENDS_SQL = (
    "SELECT m.name, d.name FROM ir_module_module m JOIN ir_module_module_dependency d "
    "ON d.module_id = m.id WHERE m.state IN ('installed', 'to upgrade') ORDER BY 1, 2"
)
TRANSIENT_SQL = "SELECT model FROM ir_model WHERE transient ORDER BY 1"
RELATED_SQL = (
    "SELECT model, name FROM ir_model_fields WHERE store AND coalesce(related, '') <> '' "
    "ORDER BY 1, 2"
)

#: The registry's own tables. Other ir_* tables (attachments, crons, parameters,
#: sequences, properties) are the client's configuration or data.
METADATA = (
    "ir_model", "ir_model_data", "ir_model_fields", "ir_model_fields_selection",
    "ir_model_constraint", "ir_model_relation", "ir_model_access", "ir_ui_view",
    "ir_ui_view_group_rel", "ir_ui_menu", "ir_ui_menu_group_rel", "ir_translation", "ir_rule",
    "rule_group_rel", "ir_module_module", "ir_module_module_dependency",
    "ir_module_module_exclusion", "ir_module_category",
)
KINDS = ("data lost", "recomputed", "module data", "wizard", "metadata", "empty", "grew")
#: A data loss the decisions file accepts by name: reported, and it does not stop the run.
ACCEPTED = "accepted"

_MODULE_RE = re.compile(r"^[a-z_][a-z0-9_]{0,63}$")
_TABLE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_COLUMN_RE = re.compile(r"^[a-z0-9_]+$")


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _module_list(modules: list[str], what: str) -> str:
    names = sorted(m for m in modules if _MODULE_RE.fullmatch(m))
    if not names:
        raise ValueError(f"no module name to {what}")
    return ", ".join(f"'{m}'" for m in names)


def owned_rows_sql(modules: list[str]) -> str:
    """Rows each model has through ``ir_model_data`` for these modules."""
    listed = _module_list(modules, "count rows for")
    return (f"SELECT model, count(*) FROM ir_model_data WHERE module IN ({listed}) "
            "GROUP BY 1 ORDER BY 1")


def fields_sql(modules: list[str]) -> str:
    """``model, field`` for every stored field these modules declare: the only columns
    their uninstall can drop from a table that stays."""
    listed = _module_list(modules, "list fields of")
    return ("SELECT DISTINCT f.model, f.name FROM ir_model_data d JOIN ir_model_fields f "
            f"ON f.id = d.res_id WHERE d.model = 'ir.model.fields' AND d.module IN ({listed}) "
            "AND f.store ORDER BY 1, 2")


def column_values_sql(columns: list[tuple[str, str]]) -> str:
    """How many rows hold a value, per ``(table, column)``: read where it still exists.

    Odoo stores an unset boolean as ``false`` and may store an unset char as
    ``''``: neither is a value anyone entered, and counting them reported every
    stock move as lost for a flag that was never set."""
    if not columns:
        raise ValueError("no column to count values for")
    return " UNION ALL ".join(
        f"SELECT '{t}', '{c}', count(*) FILTER (WHERE {_ident(c)} IS NOT NULL AND "
        f"{_ident(c)}::text NOT IN ('false', ''))::text FROM public.{_ident(t)}"
        for t, c in columns if _TABLE_RE.fullmatch(t) and _COLUMN_RE.fullmatch(c))


def model_table(model: str) -> str:
    """The table Odoo gives a model by default; a custom ``_table`` is never excused."""
    return model.replace(".", "_")


def parse_counts(rows: list[list[str]]) -> dict[str, int]:
    out = {}
    for row in rows:
        if len(row) >= 2 and row[1].strip().isdigit():
            out[row[0]] = int(row[1])
    return out


def parse_columns(rows: list[list[str]]) -> set[tuple[str, str]]:
    return {(row[0], row[1]) for row in rows if len(row) >= 2}


@dataclass(frozen=True)
class UninstallChange:
    table: str
    column: str  # "" for the table's rows
    kind: str
    before: int  # -1: a column whose values were not counted
    after: int
    owned: int = 0
    reason: str = ""

    @property
    def name(self) -> str:
        return f"{self.table}.{self.column}" if self.column else self.table


def is_metadata(table: str) -> bool:
    """The registry's tables, and this tool's own record (``odwg_*``), which the
    rehearsal's re-neutralisation writes to."""
    return table in METADATA or table.startswith(("ir_act", "ir_ui_", "odwg_"))


def is_wizard(table: str, transient_tables: set[str]) -> bool:
    """A transient model's table, or one of its many2many tables, which Odoo names
    after it (``<table>_<other>_rel``)."""
    return table in transient_tables or (
        table.endswith("_rel") and any(table.startswith(t + "_") for t in transient_tables))


def diff_uninstall(before_rows: dict[str, int], after_rows: dict[str, int],
                   before_cols: set[tuple[str, str]], after_cols: set[tuple[str, str]],
                   owned: dict[str, int], transient: set[str],
                   related: set[tuple[str, str]],
                   column_values: dict[tuple[str, str], int]) -> list[UninstallChange]:
    """Every difference an uninstall made, named.

    ``owned`` is rows per model the uninstalled modules had in ``ir_model_data``,
    ``transient`` and ``related`` are models and ``(model, field)`` pairs, all read
    from the database before; ``column_values`` counts, in that database, the
    rows holding a value in each column that is gone. A gone column it does not count
    is data lost: nothing says it was empty."""
    owned_t = {model_table(m): n for m, n in owned.items()}
    transient_t = {model_table(m) for m in transient}
    related_t = {(model_table(m), f) for m, f in related}
    changes = []
    for table, before in sorted(before_rows.items()):
        after = after_rows.get(table, 0)
        if after == before and table in after_rows:
            continue
        if is_metadata(table):
            kind = "metadata"
        elif after > before:
            kind = "grew"
        elif is_wizard(table, transient_t):
            kind = "wizard"
        elif before - after <= owned_t.get(table, 0):
            kind = "empty" if before == 0 else "module data"
        else:
            kind = "data lost"
        changes.append(UninstallChange(table, "", kind, before, after, owned_t.get(table, 0)))
    for table, column in sorted(before_cols - after_cols):
        if table not in after_rows:
            continue  # the table went, and its rows say what went with it
        values = column_values.get((table, column), -1)
        if (table, column) in related_t:
            kind = "recomputed"
        elif values == 0:
            kind = "empty"
        elif is_wizard(table, transient_t) or is_metadata(table):
            kind = "wizard" if is_wizard(table, transient_t) else "metadata"
        else:
            kind = "data lost"
        changes.append(UninstallChange(table, column, kind, values, 0))
    return changes


def taken_along(asked: list[str], installed_before: set[str],
                installed_after: set[str]) -> list[str]:
    """Modules the uninstall removed beyond the ones asked for: their dependents."""
    return sorted((installed_before - installed_after) - set(asked))


def accept(changes: list[UninstallChange], accepted: list) -> list[UninstallChange]:
    """``changes`` with each data loss that ``accepted`` (``[name, reason]``) names as
    accepted, carrying its reason. A table's name accepts its rows, not its columns."""
    reasons = {name: reason for name, reason in accepted}
    return [UninstallChange(c.table, c.column, ACCEPTED, c.before, c.after, c.owned,
                            reasons[c.name])
            if c.kind == "data lost" and c.name in reasons else c
            for c in changes]


#: Run by the source version's ``odoo-bin shell``, after ``names = <the modules>``: the
#: Apps screen's own uninstall, then a check that every module asked for is gone. Any
#: failure exits non-zero.
_UNINSTALL_BODY = (
    "mods = env['ir.module.module'].search([('name', 'in', names), ('state', '=', 'installed')])\n"
    "missing = sorted(set(names) - set(mods.mapped('name')))\n"
    "if missing:\n"
    "    raise SystemExit('not installed: ' + ', '.join(missing))\n"
    "mods.button_immediate_uninstall()\n"
    "env.cr.commit()\n"
    "env.cr.execute(\"SELECT name FROM ir_module_module WHERE name IN %s "
    "AND state <> 'uninstalled'\", (tuple(names),))\n"
    "left = [r[0] for r in env.cr.fetchall()]\n"
    "if left:\n"
    "    raise SystemExit('still installed: ' + ', '.join(left))\n"
    "print('[uninstalled] ' + ', '.join(names))\n"
)

#: The names the driver passes: the plan's, through the environment.
DRIVER_NAMES = "sorted(__import__('os').environ['ODWG_RETIRE'].split(','))"


def uninstall_script(names: str) -> str:
    """The shell script, with ``names`` a Python expression for the modules' names."""
    return f"names = {names}\n{_UNINSTALL_BODY}"


# --- the driver's entry ----------------------------------------------------------------

def _rows(path: str) -> list[list[str]]:
    with open(path, encoding="utf-8") as handle:
        return [line.rstrip("\n").split("\t") for line in handle if line.strip()]


def main_values(snapshot: str) -> int:
    """Print the SQL that counts the values of every column the retired modules' fields
    have in a table, from ``columns-before.tsv`` and ``fields.tsv``."""
    columns = parse_columns(_rows(f"{snapshot}/columns-before.tsv"))
    fields = {(model_table(r[0]), r[1]) for r in _rows(f"{snapshot}/fields.tsv") if len(r) > 1}
    wanted = sorted(columns & fields)
    print(column_values_sql(wanted) if wanted else "SELECT NULL, NULL, NULL WHERE false")
    return 0


def compare(snapshot: str, plan: dict) -> tuple[list[UninstallChange], list[str], list[str]]:
    """The changes, the modules taken along, and the retired modules still installed."""
    before_rows = parse_counts(_rows(f"{snapshot}/rows-before.tsv"))
    after_rows = parse_counts(_rows(f"{snapshot}/rows-after.tsv"))
    installed_before = {r[0] for r in _rows(f"{snapshot}/installed-before.tsv")}
    installed_after = {r[0] for r in _rows(f"{snapshot}/installed-after.tsv")}
    values = {(r[0], r[1]): int(r[2]) for r in _rows(f"{snapshot}/values.tsv")
              if len(r) > 2 and r[2].isdigit()}
    changes = diff_uninstall(
        before_rows, after_rows,
        parse_columns(_rows(f"{snapshot}/columns-before.tsv")),
        parse_columns(_rows(f"{snapshot}/columns-after.tsv")),
        parse_counts(_rows(f"{snapshot}/owned.tsv")),
        {r[0] for r in _rows(f"{snapshot}/transient.tsv")},
        {(r[0], r[1]) for r in _rows(f"{snapshot}/related.tsv") if len(r) > 1}, values)
    retired = plan["retire"]
    return (accept(changes, plan["accepted"]), taken_along(retired, installed_before,
                                                           installed_after),
            sorted(set(retired) & installed_after))


def main_compare(snapshot: str, plan_path: str, listing: str) -> int:
    """Classify what the uninstall changed, write ``listing`` (TSV), print every change
    that is not the registry's own, and exit 1 when data was lost that no one accepted,
    a module went that was not asked for, or one asked for is still installed."""
    with open(plan_path, encoding="utf-8") as handle:
        plan = json.load(handle)
    changes, along, left = compare(snapshot, plan)
    with open(listing, "w", encoding="utf-8") as handle:
        handle.write("table\tcolumn\tkind\tbefore\tafter\towned\treason\n")
        for c in changes:
            handle.write(f"{c.table}\t{c.column}\t{c.kind}\t{c.before}\t{c.after}\t{c.owned}"
                         f"\t{c.reason}\n")
    metadata = 0
    for c in changes:
        if c.kind == "metadata":
            metadata += 1
            continue
        why = f" ({c.reason})" if c.reason else ""
        before = "?" if c.before < 0 else c.before
        print(f"[retire] {c.kind}: {c.name} {before} -> {c.after}{why}")
    print(f"[retire] {metadata} registry tables changed (models, fields, views, menus, rules)")
    lost = [c.name for c in changes if c.kind == "data lost"]
    for name in lost:
        print(f"[retire] DATA LOST, not accepted: {name}", file=sys.stderr)
    if along:
        print(f"[retire] the uninstall also removed: {', '.join(along)}", file=sys.stderr)
    if left:
        print(f"[retire] still installed: {', '.join(left)}", file=sys.stderr)
    return 1 if lost or along or left else 0


def main(argv: list[str]) -> int:
    """``sql owned|fields MODULES``, ``values SNAPSHOT_DIR`` or
    ``compare SNAPSHOT_DIR PLAN LISTING``; MODULES is comma-separated."""
    if argv[:1] == ["sql"] and len(argv) == 3 and argv[1] in ("owned", "fields"):
        build = owned_rows_sql if argv[1] == "owned" else fields_sql
        print(build(argv[2].split(",")))
        return 0
    if argv[:1] == ["values"] and len(argv) == 2:
        return main_values(argv[1])
    if argv[:1] == ["compare"] and len(argv) == 4:
        return main_compare(*argv[1:])
    print("usage: retire.py sql owned|fields MODULES | values DIR | "
          "compare DIR PLAN LISTING", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
