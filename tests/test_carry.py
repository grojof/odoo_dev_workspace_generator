"""The client-modules stage's plan (carry.py), its commands, and its place in the driver."""

from __future__ import annotations

import json

from odoo_dwg import carry, templates
from odoo_dwg.models import MigrationEnv, ModuleDecision, decisions_from_json, decisions_to_json
from odoo_dwg.workflows import checks, decide


def _entry(module, kind, to=None, source="12.0", target="18.0"):
    entry = {"module": module, "source": source, "target": target, "decision": kind}
    if to is not None:
        entry["to"] = to
    return entry


def _reader(modules: dict):
    """``read`` over an invented target: name -> manifest (None = unreadable), with
    ``migrations`` true unless the manifest says ``"_no_migrations": True``."""

    def read(name):
        if name not in modules:
            return None
        manifest = modules[name]
        migrations = not (manifest or {}).get("_no_migrations")
        return {"path": f"/src/{name}", "manifest": manifest, "migrations": migrations}

    return read


TARGET = {
    "acme_sale": {"version": "18.0.1.0.0"},
    "acme_stock": {"version": "18.0.1.0.0"},
    "stock_inventory": {"version": "18.0.1.1.2"},
    "sale": {"version": "1.2"},
}


def test_renames_fold_several_modules_into_one():
    entries = [_entry("pack_line", "renamed", "acme_sale"),
               _entry("picking_installer", "renamed", "acme_stock"),
               _entry("picking_origin_link", "renamed", "acme_stock")]
    result = carry.plan(entries, "12.0", "18.0", _reader(TARGET))
    assert result["renames"] == [["pack_line", "acme_sale"],
                                 ["picking_installer", "acme_stock"],
                                 ["picking_origin_link", "acme_stock"]]
    assert result["merges"] == ["acme_stock"]
    assert result["updates"] == ["acme_sale", "acme_stock"]
    assert not carry.blocked(result) and carry.has_work(result)


def test_replaced_installs_first_and_uninstalls_the_old_module():
    entries = [_entry("old_inventory_numbering", "replaced", ["stock_inventory"]),
               _entry("old_glue", "dropped")]
    result = carry.plan(entries, "12.0", "18.0", _reader(TARGET),
                        installed={"old_inventory_numbering", "old_glue"})
    assert result["installs"] == ["stock_inventory"]
    assert result["uninstalls"] == ["old_glue", "old_inventory_numbering"]


def test_a_replacement_already_installed_is_not_installed_again():
    result = carry.plan([_entry("old", "replaced", ["sale"])], "12.0", "18.0", _reader(TARGET),
                        installed={"old", "sale"})
    assert result["installs"] == [] and result["uninstalls"] == ["old"]


def test_a_rename_onto_an_installed_module_is_a_merge_that_runs_no_scripts():
    result = carry.plan([_entry("old", "renamed", "acme_sale")], "12.0", "18.0",
                        _reader(TARGET), installed={"old", "acme_sale"})
    assert result["merges"] == ["acme_sale"] and not carry.blocked(result)
    assert _codes(result) == {("old", "warning", "merge-installed")}


def test_a_module_odoo_would_not_install_blocks():
    read = _reader({"acme_sale": {"version": "18.0.1.0.0", "installable": False}})
    result = carry.plan([_entry("old", "renamed", "acme_sale")], "12.0", "18.0", read)
    assert carry.blocked(result) and result["renames"] == []


def test_modules_not_installed_are_skipped_and_named():
    result = carry.plan([_entry("gone", "renamed", "acme_sale"), _entry("gone2", "dropped")],
                        "12.0", "18.0", _reader(TARGET), installed=set())
    assert result["skipped"] == ["gone", "gone2"]
    assert not carry.has_work(result)


def test_kept_modules_left_without_code_are_named():
    result = carry.plan([_entry("codeless", "kept"), _entry("acme_sale", "deferred")],
                        "12.0", "18.0", _reader(TARGET), installed={"codeless", "acme_sale"})
    assert result["left"] == ["codeless"]


def test_only_the_pair_is_planned():
    entries = [_entry("old", "renamed", "acme_sale", target="17.0")]
    assert not carry.has_work(carry.plan(entries, "12.0", "18.0", _reader(TARGET)))


def _codes(result):
    return {(p["module"], p["level"], p["code"]) for p in result["problems"]}


def test_what_stops_the_stage():
    entries = [
        _entry("a", "renamed"),                           # no `to`
        _entry("b", "renamed", ["acme_sale", "acme_stock"]),
        _entry("c", "dropped", "acme_sale"),               # `to` on the wrong kind
        _entry("d", "renamed", "Bad-Name"),
        _entry("e", "renamed", "e"),
        _entry("f", "renamed", "not_on_disk"),
        _entry("g", "renamed", "unreadable"),
        _entry("h", "replaced", ["old_series"]),
    ]
    read = _reader({**TARGET, "unreadable": None, "old_series": {"version": "12.0.1.0.0"}})
    result = carry.plan(entries, "12.0", "18.0", read)
    assert _codes(result) == {
        ("a", "blocking", "no-to"), ("b", "blocking", "many-to"),
        ("c", "blocking", "to-on-kind"), ("d", "blocking", "bad-name"),
        ("e", "blocking", "to-itself"), ("f", "blocking", "unresolved"),
        ("g", "blocking", "no-manifest"), ("h", "blocking", "wrong-series"),
    }
    assert carry.blocked(result)
    # A decision that is wrong on its own is not planned at all.
    assert all(old not in {"a", "b", "c", "d", "e"} for old, _ in result["renames"])


def test_warnings_do_not_stop_the_stage():
    read = _reader({"acme_sale": {"version": "18.0.1.0.0", "_no_migrations": True}})
    result = carry.plan([_entry("old", "renamed", "acme_sale"), _entry("x", "kept installed")],
                        "12.0", "18.0", read)
    assert _codes(result) == {("old", "warning", "no-migrations"),
                              ("x", "warning", "unknown-kind")}
    assert not carry.blocked(result)


def test_every_problem_code_has_a_message():
    for code, text in carry.MESSAGES.items():
        args = [f"arg{index}" for index in range(text.count("{}"))]
        assert all(arg in carry.message({"code": code, "args": args}) for arg in args)


def test_describe_names_merges_and_problems():
    result = carry.plan([_entry("a", "renamed", "acme_stock"), _entry("b", "renamed", "acme_stock"),
                         _entry("c", "renamed", "missing")], "12.0", "18.0", _reader(TARGET))
    lines = carry.describe(result)
    assert "a merged into acme_stock" in lines
    assert "update: acme_stock" in lines
    assert all("c renamed" not in line for line in lines)
    assert "c: missing resolves in none of the 18.0 sources (blocking)" in lines


def test_the_reader_parses_manifests_without_running_them(tmp_path):
    (tmp_path / "custom" / "acme_sale" / "migrations").mkdir(parents=True)
    (tmp_path / "custom" / "acme_sale" / "__manifest__.py").write_text(
        "{'name': 'ACME sale', 'version': '18.0.1.0.0'}")
    (tmp_path / "core" / "broken").mkdir(parents=True)
    (tmp_path / "core" / "broken" / "__manifest__.py").write_text("import os")
    read = carry.reader([str(tmp_path / "custom"), str(tmp_path / "core")])
    assert read("acme_sale")["manifest"]["version"] == "18.0.1.0.0"
    assert read("acme_sale")["migrations"] is True
    assert read("broken")["manifest"] is None
    assert read("nowhere") is None


def test_main_is_the_drivers_entry(tmp_path, monkeypatch, capsys):
    (tmp_path / "src" / "acme_sale").mkdir(parents=True)
    (tmp_path / "src" / "acme_sale" / "__manifest__.py").write_text("{'version': '18.0.1.0.0'}")
    decisions = tmp_path / "decisions.json"
    decisions.write_text(json.dumps({"decisions": [_entry("pack_line", "renamed", "acme_sale")]}))
    plan_file = tmp_path / "plan.json"
    argv = [str(decisions), "12.0", "18.0", str(plan_file), str(tmp_path / "src")]
    monkeypatch.setenv("ODWG_INSTALLED", "pack_line\nbase\n")
    assert carry.main(argv) == 0
    out = capsys.readouterr()
    assert out.out.splitlines() == ["acme_sale", ""]
    assert "[modules] pack_line renamed to acme_sale" in out.err
    assert json.loads(plan_file.read_text())["renames"] == [["pack_line", "acme_sale"]]
    monkeypatch.setenv("ODWG_INSTALLED", "base\n")
    assert carry.main(argv) == 3
    decisions.write_text(json.dumps([_entry("pack_line", "renamed", "missing")]))
    monkeypatch.delenv("ODWG_INSTALLED")
    assert carry.main(argv) == 1
    decisions.write_text("{not json")
    assert carry.main(argv) == 3


# --- the decisions file ----------------------------------------------------------------


def test_a_decision_keeps_its_to_through_the_file():
    text = json.dumps({"decisions": [_entry("a", "renamed", "acme_sale"),
                                     _entry("b", "replaced", ["x", "y"]),
                                     _entry("c", "dropped")]})
    decisions = decisions_from_json(text)
    assert [d.to for d in decisions] == [("acme_sale",), ("x", "y"), ()]
    again = json.loads(decisions_to_json(decisions))["decisions"]
    assert again[0]["to"] == "acme_sale" and again[1]["to"] == ["x", "y"]
    assert "to" not in again[2]


def test_an_older_decisions_file_reads_as_before():
    decision = ModuleDecision.from_dict(
        {"module": "m", "source": "12.0", "target": "18.0", "decision": "dropped"})
    assert decision is not None and decision.to == ()
    assert "to" not in decision.to_dict()


def test_decide_replaces_the_modules_entry_in_place():
    text = json.dumps({"note": "mine", "decisions": [
        _entry("a", "deferred"), _entry("b", "dropped"), _entry("a", "deferred", target="17.0")]})
    entry = decide.build_entry("a", "12.0", "18.0", "renamed", ["acme_sale"], "ported", "2026-09-25")
    data = json.loads(decide.merged(text, entry))
    assert data["note"] == "mine"
    assert [e["module"] for e in data["decisions"]] == ["a", "b", "a"]
    assert data["decisions"][0]["to"] == "acme_sale"
    assert data["decisions"][0]["evidence"] == {"checked": "2026-09-25",
                                                "recorded_by": "migrate decide"}
    assert data["decisions"][2]["decision"] == "deferred"


def test_decide_appends_and_keeps_a_bare_list():
    entry = decide.build_entry("n", "12.0", "18.0", "replaced", ["x"], "", "2026-09-25")
    data = json.loads(decide.merged(json.dumps([_entry("a", "kept")]), entry))
    assert isinstance(data, list) and data[1]["to"] == ["x"]
    assert json.loads(decide.merged("", entry)) == {"decisions": [entry]}


def test_decide_refuses_an_unreadable_file():
    entry = decide.build_entry("n", "12.0", "18.0", "dropped", [], "", "2026-09-25")
    for text in ("{broken", '{"decisions": 3}'):
        try:
            decide.merged(text, entry)
        except ValueError:
            continue
        raise AssertionError(f"accepted {text!r}")


def _environment_at(tmp_path, monkeypatch):
    monkeypatch.setattr(MigrationEnv, "base_dir", str(tmp_path))
    env = MigrationEnv(source="12.0", target="18.0")
    env.root.mkdir(parents=True)
    return env


def test_decide_prints_without_writing(tmp_path, monkeypatch, capsys):
    _environment_at(tmp_path, monkeypatch)
    applied = []
    monkeypatch.setattr(decide, "apply_commands", applied.append)
    code = decide.record_decision("old", "12.0", "18.0", "renamed", ["acme_sale"], "", write=False)
    assert code == checks.CLEAN and applied == []
    assert '"to": "acme_sale"' in capsys.readouterr().out
    assert decide.record_decision("old", "12.0", "18.0", "renamed", ["acme_sale"], "",
                                  write=True) == checks.CLEAN
    assert len(applied) == 1


def test_decide_writes_through_a_link_and_keeps_the_mode(tmp_path, monkeypatch):
    env = _environment_at(tmp_path, monkeypatch)
    shared = tmp_path / "shared-decisions.json"
    shared.write_text('{"decisions": []}')
    shared.chmod(0o600)
    env.decisions_file.symlink_to(shared)
    applied = []
    monkeypatch.setattr(decide, "apply_commands", applied.append)
    decide.record_decision("old", "12.0", "18.0", "dropped", [], "", write=True)
    command = applied[0][0].command
    assert str(shared) in command and "chmod 600" in command


def test_decide_refuses_a_file_it_cannot_read(tmp_path, monkeypatch):
    env = _environment_at(tmp_path, monkeypatch)
    env.decisions_file.write_text('{"decisions": []}')
    monkeypatch.setattr(decide, "read_text", lambda path: None)
    applied = []
    monkeypatch.setattr(decide, "apply_commands", applied.append)
    assert decide.record_decision("old", "12.0", "18.0", "dropped", [], "", write=True) \
        == checks.UNKNOWN
    assert applied == []


def test_decide_needs_an_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(MigrationEnv, "base_dir", str(tmp_path))
    assert decide.record_decision("old", "12.0", "18.0", "dropped", [], "", write=True) \
        == checks.UNKNOWN


def test_decide_refuses_a_rename_without_target(monkeypatch):
    applied = []
    monkeypatch.setattr(decide, "apply_commands", applied.append)
    assert decide.record_decision("old", "12.0", "18.0", "renamed", [], "", write=True) \
        == checks.FOUND
    assert decide.record_decision("Old-Name", "12.0", "18.0", "dropped", [], "", write=True) \
        == checks.FOUND
    assert applied == []


# --- migrate modules --------------------------------------------------------------------


def test_migrate_modules_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(checks.carry, "read_decisions",
                        lambda path: [_entry("pack_line", "renamed", "acme_sale")])
    monkeypatch.setattr(checks.carry, "reader", lambda sources: _reader(TARGET))
    monkeypatch.setattr(checks.migration, "env_as_generated",
                        lambda source, target: MigrationEnv(source=source, target=target))
    assert checks.client_modules("12.0", "18.0", None, "h", 5432, "u") == checks.CLEAN
    assert "pack_line is renamed to acme_sale" in capsys.readouterr().out
    monkeypatch.setattr(checks, "psql_rows", lambda *args, **kwargs: None)
    assert checks.client_modules("12.0", "18.0", "acme_copy", "h", 5432, "u") == checks.UNKNOWN
    monkeypatch.setattr(checks, "psql_rows", lambda *args, **kwargs: [["base"]])
    assert checks.client_modules("12.0", "18.0", "acme_copy", "h", 5432, "u") == checks.CLEAN
    assert "Nothing to carry" in capsys.readouterr().out
    monkeypatch.setattr(checks.carry, "read_decisions",
                        lambda path: [_entry("pack_line", "renamed", "missing")])
    assert checks.client_modules("12.0", "18.0", None, "h", 5432, "u") == checks.FOUND
    assert checks.client_modules("12.0", "18.0", "bad name;", "h", 5432, "u") == checks.UNKNOWN
    monkeypatch.setattr(checks.migration, "env_as_generated",
                        lambda source, target: MigrationEnv(source=source, target=target)
                        .validate())
    assert checks.client_modules("12.0", "11.0", None, "h", 5432, "u") == checks.UNKNOWN


# --- the driver ---------------------------------------------------------------------------


def _driver():
    return templates.render_run_migration_sh(MigrationEnv(source="12.0", target="18.0"))


def test_the_driver_embeds_carry_verbatim():
    sh = _driver()
    embedded = sh.split("<<'ODWG_CARRY'\n", 1)[1].split("ODWG_CARRY\n", 1)[0]
    assert embedded == templates.carry_source()
    assert templates.carry_source().startswith('"""The client-modules stage')


def test_the_stage_runs_after_the_target_step_in_order():
    sh = _driver()
    target_done = sh.index('mark "18.0" ok\n  AT_TARGET=1\n  rm -f "$MODULES_DIRTY"\nfi')
    stage = sh.index("# --- stage: the client's modules at 18.0")
    order = [sh.index(marker, stage) for marker in (
        'step_hook "18.0-modules" pre', "update_module_names(env.cr, pairs, merge_modules=True)",
        '${UPDATES:+-u "$UPDATES"} ${INSTALLS:+-i "$INSTALLS"} --stop-after-init',
        "button_immediate_uninstall()", 'step_hook "18.0-modules" post',
        'neutralise "18.0-modules"', 'checkpoint "18.0-modules"', 'mark "18.0-modules" ok')]
    assert target_done < stage and order == sorted(order)
    assert sh.index('mark - run-ok') > order[-1]


def test_the_stage_runs_plain_odoo():
    stage = _driver().split("# --- stage: the client's modules", 1)[1]
    assert "openupgrade_framework" not in stage and "--upgrade-path" not in stage


def test_the_uninstall_refuses_to_take_another_module_along():
    stage = _driver().split("# --- stage: the client's modules", 1)[1]
    guard = stage.index("modules.downstream_dependencies() - modules")
    assert guard < stage.index("button_immediate_uninstall()")
    assert "raise SystemExit(1)" in stage[guard:stage.index("button_immediate_uninstall()")]


def test_nothing_to_carry_writes_no_checkpoint():
    stage = _driver().split("# --- stage: the client's modules", 1)[1]
    nothing = stage.index('mark "18.0-modules" skip "nothing to carry"')
    assert 'checkpoint "18.0-modules"' not in stage[:nothing]


def test_a_database_an_earlier_carry_changed_is_restored_first():
    stage = _driver().split("# --- stage: the client's modules", 1)[1]
    restore = stage.index('if [ "$AT_TARGET" != 1 ] && [ -f "$MODULES_DIRTY" ]; then')
    # Before anything is decided, even that there is nothing to carry.
    assert restore < stage.index('restore_ck "18.0"') < stage.index("carry >")
    assert stage.index("carry >") < stage.index(': > "$MODULES_DIRTY"') \
        < stage.index('step_hook "18.0-modules" pre')
    assert stage.index('checkpoint "18.0-modules"') < stage.rindex('rm -f "$MODULES_DIRTY"')


def test_stage_failures_are_recorded_as_failures():
    stage = _driver().split("# --- stage: the client's modules", 1)[1]
    assert 'modules_fail() { mark "18.0-modules" fail "$1"; die "18.0-modules: $2"; }' in stage
    for failure in ("|| modules_fail hook", "|| modules_fail rename", "|| modules_fail uninstall",
                    '|| modules_fail "$code"'):
        assert failure in stage, failure


def test_nothing_is_uninstalled_unless_everything_was_installed():
    stage = _driver().split("# --- stage: the client's modules", 1)[1]
    check = stage.index("if wanted - done:")
    assert check < stage.index("button_immediate_uninstall()")


def test_redo_modules_and_the_resume():
    sh = _driver()
    assert 'MODULES_CK=18.0-modules' in sh
    assert '--redo-modules) REDO_MODULES=1 ;;' in sh
    redo = sh.index('if [ "$REDO_MODULES" = 1 ]; then\n    # The working database')
    # Only once the checkpoints are known to be this dump's.
    assert sh.index("came from another source dump") < redo
    assert redo < sh.index('if [ "$gap" = 0 ] && have_ck "$MODULES_CK"; then')
    assert ': > "$MODULES_DIRTY"' in sh[redo:redo + 300]
    assert 'rm -f "$CK"/*.dump "$CK"/*.dump.tmp "$CK"/*.dirty' in sh
    assert 'if [ "$LAST" = "18.0" ] || [ "$LAST" = "$MODULES_CK" ]; then' in sh
