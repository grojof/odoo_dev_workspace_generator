"""The modules retired before the chain: the guard's rules and its place in the driver."""

from __future__ import annotations

import json

import pytest

from odoo_dwg import planners, retire, templates
from odoo_dwg.models import MigrationEnv


def _write(directory, name: str, rows: list[list[str]]) -> None:
    (directory / f"{name}.tsv").write_text("".join("\t".join(r) + "\n" for r in rows))


def _snapshot(directory, *, rows_after=None, values=None, installed_after=None) -> None:
    _write(directory, "rows-before", [["res_partner", "10"], ["old_log", "3"],
                                      ["ir_ui_view", "50"], ["old_wizard", "2"],
                                      ["res_groups", "5"]])
    _write(directory, "rows-after", rows_after or [["res_partner", "10"], ["ir_ui_view", "40"],
                                                   ["res_groups", "4"]])
    _write(directory, "columns-before", [["res_partner", "id"], ["res_partner", "old_flag"],
                                         ["res_partner", "old_note"]])
    _write(directory, "columns-after", [["res_partner", "id"]])
    _write(directory, "installed-before", [["base"], ["old_x"]])
    _write(directory, "installed-after", installed_after or [["base"]])
    _write(directory, "owned", [["res.groups", "1"]])
    _write(directory, "transient", [["old.wizard"]])
    _write(directory, "related", [])
    _write(directory, "fields", [["res.partner", "old_flag"], ["res.partner", "old_note"],
                                 ["old.log", "name"]])
    _write(directory, "values", values or [["res_partner", "old_flag", "0"],
                                           ["res_partner", "old_note", "4"]])


def _plan(tmp_path, accepted) -> str:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"retire": ["old_x"], "accepted": accepted}))
    return str(path)


def _listing(path) -> dict:
    lines = path.read_text().splitlines()
    assert lines[0] == "table\tcolumn\tkind\tbefore\tafter\towned\treason"
    return {(r[0], r[1]): r for r in (line.split("\t") for line in lines[1:])}


def test_data_no_one_accepted_stops_it_and_every_change_is_listed(tmp_path, capsys):
    _snapshot(tmp_path)
    out = tmp_path / "retired.tsv"
    assert retire.main(["compare", str(tmp_path), _plan(tmp_path, []), str(out)]) == 1
    rows = _listing(out)
    assert rows[("old_log", "")][2:5] == ["data lost", "3", "0"]
    assert rows[("res_partner", "old_note")][2:4] == ["data lost", "4"]
    assert rows[("res_partner", "old_flag")][2] == "empty"
    assert rows[("old_wizard", "")][2] == "wizard"
    assert rows[("res_groups", "")][2] == "module data"
    assert rows[("ir_ui_view", "")][2] == "metadata"
    err = capsys.readouterr().err
    assert "DATA LOST, not accepted: old_log" in err
    assert "DATA LOST, not accepted: res_partner.old_note" in err


def test_accepted_losses_carry_their_reason_and_let_it_go_on(tmp_path, capsys):
    _snapshot(tmp_path)
    out = tmp_path / "retired.tsv"
    plan = _plan(tmp_path, [["old_log", "a log"], ["res_partner.old_note", "a note"]])
    assert retire.main(["compare", str(tmp_path), plan, str(out)]) == 0
    rows = _listing(out)
    assert rows[("old_log", "")][2] == "accepted" and rows[("old_log", "")][6] == "a log"
    assert rows[("res_partner", "old_note")][6] == "a note"
    printed = capsys.readouterr().out
    assert "[retire] accepted: old_log 3 -> 0 (a log)" in printed
    assert "ir_ui_view" not in printed  # the registry is counted, not listed


def test_a_table_name_does_not_accept_its_columns():
    change = retire.UninstallChange("res_partner", "old_note", "data lost", 4, 0)
    assert retire.accept([change], [["res_partner", "why"]])[0].kind == "data lost"


def test_a_gone_column_nobody_counted_is_data_lost():
    changes = retire.diff_uninstall({"t": 1}, {"t": 1}, {("t", "id"), ("t", "c")}, {("t", "id")},
                                    {}, set(), set(), {})
    assert [(c.name, c.kind, c.before) for c in changes] == [("t.c", "data lost", -1)]


def test_a_module_taken_along_or_left_installed_stops_it(tmp_path, capsys):
    _snapshot(tmp_path, installed_after=[["old_x"]])
    plan = _plan(tmp_path, [["old_log", "a"], ["res_partner.old_note", "b"]])
    assert retire.main(["compare", str(tmp_path), plan, str(tmp_path / "l.tsv")]) == 1
    err = capsys.readouterr().err
    assert "also removed: base" in err and "still installed: old_x" in err


def test_the_values_query_counts_only_the_retired_modules_columns_that_exist(tmp_path, capsys):
    _snapshot(tmp_path)
    assert retire.main(["values", str(tmp_path)]) == 0
    sql = capsys.readouterr().out
    assert "'res_partner', 'old_flag'" in sql and "'res_partner', 'old_note'" in sql
    assert "old_log" not in sql  # a whole table's rows say what went with it
    _write(tmp_path, "fields", [])
    retire.main(["values", str(tmp_path)])
    assert capsys.readouterr().out.strip() == "SELECT NULL, NULL, NULL WHERE false"


def test_the_runtime_queries_take_only_module_names(capsys):
    assert retire.main(["sql", "fields", "old_x,x'); DROP"]) == 0
    sql = capsys.readouterr().out
    assert "'old_x'" in sql and "DROP" not in sql and "f.store" in sql
    with pytest.raises(ValueError):
        retire.owned_rows_sql(["x'); DROP"])
    assert retire.main(["nonsense"]) == 2


def test_the_driver_and_the_rehearsal_run_the_same_uninstall():
    rehearsal = planners.uninstall_script(["b", "a"])
    driver = retire.uninstall_script(retire.DRIVER_NAMES)
    assert rehearsal.split("\n", 1)[1] == driver.split("\n", 1)[1]
    assert rehearsal.startswith("names = ['a', 'b']\n")
    assert "ODWG_RETIRE" in driver.splitlines()[0]


# --- the driver ---------------------------------------------------------------------------


def _driver() -> str:
    return templates.render_run_migration_sh(MigrationEnv(source="12.0", target="18.0"))


def test_the_driver_embeds_retire_and_carry_once_each():
    sh = _driver()
    embedded = sh.split("<<'ODWG_RETIRE'\n", 1)[1].split("ODWG_RETIRE\n", 1)[0]
    assert embedded == templates.retire_source()
    assert sh.count("<<'ODWG_CARRY'") == 1


def test_it_retires_after_the_restore_and_before_anything_reads_the_source():
    sh = _driver()
    fresh = sh.index("if ! have_ck 00_source; then")
    order = [sh.index(marker, fresh) for marker in (
        'pg_restore --no-owner --dbname "$DB" "$SRC_DUMP"', "retire_before_chain",
        "preflight_db", "neutralise 00_source", "checkpoint 00_source")]
    assert order == sorted(order)
    assert sh.index("retire_before_chain() {") < fresh
    resumed = sh.split("if ! have_ck 00_source; then", 1)[1].split("\nelse\n", 1)[1]
    assert "retire_before_chain" not in resumed.split("\nfi\n", 1)[0]


def test_the_stage_uninstalls_with_the_sources_own_odoo_between_its_snapshots():
    env = MigrationEnv(source="12.0", target="18.0")
    stage = _driver().split("retire_before_chain() {", 1)[1].split("\n}\n", 1)[0]
    order = [stage.index(marker) for marker in (
        "carry_py retire", "neutralise retire", "retire_snap rows-before",
        "retire_snap values", f"{env.source_odoo_bin} shell", "retire_snap rows-after",
        "retire_py compare", "mark 00_source retired")]
    assert order == sorted(order)
    assert "--no-http --max-cron-threads=0" in stage
    assert str(env.config_file("12.0")) in stage
