"""The rehearsal tester: what it harvests, what it chooses, and what it concludes.

The analysis lines here are copied verbatim from OpenUpgrade's own
`upgrade_analysis.txt` files. A fixture written from memory would test this
project's idea of the format rather than the format.
"""

from __future__ import annotations

from odoo_dwg import analysis, templates, tester

FIELDS = """---Fields in module 'sale'---
sale         / sale.order.line          / qty_delivered_manual (float)  : DEL
sale         / sale.order               / show_update_pricelist (boolean): not stored anymore
sale         / sale.order               / amount_total (monetary)       : is now stored
sale         / sale.order.line          / qty_delivered (float)         : not a function anymore
sale         / sale.order.line          / price_unit (float)            : now a function
sale         / sale.order.line          / product_template_id (many2one): not related anymore
sale         / sale.order               / note (text)                   : now related
sale         / account.move             / partner_shipping_id (many2one): module is now 'account' ('sale')
sale         / sale.order.line          / tax_id (many2many)            : NEW relation: account.tax
"""


def _kinds(text: str) -> dict[str, str]:
    return {record.field or record.model: record.kind for record in analysis.harvest_changes(text)}


def test_no_status_is_claimed_by_two_patterns():
    # The classes are decided by substring, so the risk is one pattern eating
    # another's lines. Then the order of the table would start deciding the
    # answer, which is not something a reader could see.
    for line in FIELDS.splitlines():
        row = analysis._FIELD_ROW_RE.match(line.strip())
        if not row:
            continue
        status = row.group("status")
        matched = [name for token, name in analysis._FIELD_STATUS_CLASSES if token in status]
        assert len(matched) <= 1, f"{status!r} matched {matched}"


def test_a_negative_status_is_not_read_as_its_positive():
    kinds = _kinds(FIELDS)
    assert kinds["show_update_pricelist"] == "unstored_field"
    assert kinds["amount_total"] == "stored_field"
    assert kinds["qty_delivered"] == "unfunction_field"
    assert kinds["price_unit"] == "function_field"
    assert kinds["product_template_id"] == "unrelated_field"
    assert kinds["note"] == "related_field"


def test_a_new_field_is_not_a_change_to_be_probed():
    # NEW is upgrade information: nothing that existed was taken away.
    assert "tax_id" not in _kinds(FIELDS)


def test_an_obsolete_model_that_was_renamed_is_told_from_one_that_is_gone():
    kinds = _kinds(
        "---Models in module 'base'---\n"
        "obsolete model base.update.translations [transient]\n"
        "obsolete model sale.payment.acquirer.onboarding.wizard "
        "(renamed to sale.payment.provider.onboarding.wizard) [transient]\n"
    )
    assert kinds["base.update.translations"] == "removed_model"
    assert kinds["sale.payment.acquirer.onboarding.wizard"] == "renamed_model"


def test_the_breaking_reader_is_left_as_it_was():
    # `parse_analysis` feeds the staging scan, which searches source for names
    # that break a reference. Harvesting the quiet classes must not widen it.
    records = analysis.parse_analysis(FIELDS)
    assert {record.name for record in records} == {"qty_delivered_manual"}


def test_the_same_chain_always_chooses_the_same_probes():
    by_version = {"16.0": analysis.harvest_changes(FIELDS)}
    first, _ = tester.choose_probes(by_version)
    second, _ = tester.choose_probes(by_version)
    assert [probe.name for probe in first] == [probe.name for probe in second]


def test_a_class_the_chain_never_exercises_is_named_not_dropped():
    _, uncovered = tester.choose_probes({"16.0": analysis.harvest_changes(FIELDS)})
    # This fixture has no obsolete model and no selection change.
    assert "removed_model" in uncovered and "selection_changed" in uncovered


def test_a_probe_is_preferred_from_a_core_module():
    line = "{module}         / a.model / f_{module} (float)  : DEL\n"
    text = "---Fields in module 'x'---\n" + line.format(module="l10n_br") + line.format(module="sale")
    probes, _ = tester.choose_probes({"16.0": analysis.harvest_changes(text)})
    # A tester depending on a Brazilian chart of accounts tests that chart.
    assert [probe.field for probe in probes] == ["f_sale"]


def _probe(kind: str, model: str = "sale.order", field: str = "") -> tester.Probe:
    return tester.Probe(name=f"p_{kind}", kind=kind, version="16.0", model=model,
                        field=field, detail="from the analysis file")


def test_the_four_verdicts():
    gone = _probe("removed_field", field="qty_delivered_manual")
    quiet = _probe("moved_field", field="partner_shipping_id")
    # The model row belongs in any fixture judging a field: without it the
    # probe reports that nothing was there to lose.
    model = ["model", "sale.order", ""]
    present = [model,
               ["field", "sale.order", "qty_delivered_manual"],
               ["field", "sale.order", "partner_shipping_id"]]
    states = {v.probe.name: v.state for v in tester.read_probe_states([gone, quiet], present)}
    assert states["p_removed_field"] == "still there"   # a script did not run
    assert states["p_moved_field"] == "intact"
    states = {v.probe.name: v.state for v in tester.read_probe_states([gone, quiet], [model])}
    assert states["p_removed_field"] == "gone as predicted"
    assert states["p_moved_field"] == "gone unannounced"  # the quiet loss


def test_the_findings_come_first():
    verdicts = tester.read_probe_states(
        [_probe("moved_field", field="a"), _probe("removed_field", field="b"),
         _probe("unstored_field", field="c")],
        [["model", "sale.order", ""],
         ["field", "sale.order", "b"], ["field", "sale.order", "c"]],
    )
    # The one that behaved is last, whatever it is: findings are what this is for.
    assert verdicts[-1].state == "intact" and not verdicts[-1].is_finding
    verdicts = verdicts[:2]
    # A silent disappearance before a script that did not run: the first loses
    # data with nothing saying so, the second leaves the structure recoverable.
    assert [v.state for v in verdicts] == ["gone unannounced", "still there"]
    assert all(v.is_finding for v in verdicts)


def test_a_tester_that_did_not_install_is_not_read_as_passing():
    verdicts = tester.read_probe_states([_probe("removed_field", field="a")], [], installed=False)
    assert [v.state for v in verdicts] == ["absent"]
    assert not verdicts[0].is_finding  # it is not a finding about the subject


def test_probe_rows_from_another_version_of_this_tool_are_skipped():
    rows = [["p1", "removed_field", "16.0", "sale.order", "x", "line"],
            ["p2", "a_class_this_version_does_not_know", "16.0", "sale.order", "y", "line"],
            ["p3", "removed_field", "16.0"]]
    assert [probe.name for probe in tester.probes_from_rows(rows)] == ["p1"]


def test_the_generated_module_ships_no_menu_and_no_auto_install():
    probes, uncovered = tester.choose_probes({"16.0": analysis.harvest_changes(FIELDS)})
    files = templates.render_tester_module(probes, uncovered, "12.0 - 19.0")
    manifest = files["__manifest__.py"]
    assert "auto_install" not in manifest and '"depends": ["base"]' in manifest
    assert "menu" not in files["data/probes.xml"]
    # The classes it does not cover are stated where an operator will read them.
    assert "Classes this chain never exercises" in manifest


def test_a_module_subject_is_asked_of_the_module_table_not_the_model_table():
    probe = tester.Probe(
        name="p", kind="merged_module", version="14.0",
        model="website_sale_product_style_badge", field="",
        detail="merged into website_sale",
    )
    assert probe.subject_kind == "module"
    sql = tester.probe_state_sql([probe])
    # Asking ir_model about a module reports every module as gone.
    assert "ir_module_module" in sql and "FROM ir_model WHERE" not in sql
    # A row that survives as "uninstalled" is not a module still there for
    # anything that depended on it.
    assert "state != 'uninstalled'" in sql


def test_a_module_that_was_absorbed_is_expected_to_be_gone():
    probe = tester.Probe(name="p", kind="merged_module", version="14.0",
                         model="old_module", field="", detail="d")
    assert probe.expected_gone
    gone = tester.read_probe_states([probe], [])
    assert gone[0].state == "gone as predicted" and not gone[0].is_finding
    still = tester.read_probe_states([probe], [["module", "old_module", ""]])
    assert still[0].state == "still there" and still[0].is_finding


def test_the_tester_is_written_for_the_source_version_too(tmp_path):
    from odoo_dwg import planners
    from odoo_dwg.models import MigrationEnv
    MigrationEnv.base_dir = str(tmp_path / "envs")
    env = MigrationEnv(source="12.0", target="14.0")
    probes, uncovered = tester.choose_probes({"13.0": analysis.harvest_changes(FIELDS)})
    written = " ".join(c.command for c in planners.plan_generate_tester(env, probes, uncovered))
    # Installed at the source, so its records travel; found at every step, or
    # `-u all` meets an installed module it cannot load.
    for major in ("odoo12", "odoo13", "odoo14"):
        assert f"{major}/custom/{tester.TESTER_MODULE}" in written


def test_the_generated_manifest_says_who_it_is_by():
    # Odoo attributes a manifest with no `author` to "Odoo S.A.", which is false
    # here — and coverage reads that column to decide whether a missing module is
    # Odoo's own dropped code (a warning) or somebody else's (blocking), so the
    # omission downgraded the tester's own absence to a warning. Seen on a real
    # 12 -> 14 run: "odwg_migration_tester ... Odoo dropped it".
    probes, uncovered = tester.choose_probes({"16.0": analysis.harvest_changes(FIELDS)})
    manifest = templates.render_tester_module(probes, uncovered, "12.0 - 19.0")["__manifest__.py"]
    assert f'"author": "{templates.TESTER_AUTHOR}"' in manifest
    assert templates.TESTER_AUTHOR.lower() not in ("odoo", "odoo s.a.", "odoo sa")


def _module_probe(name: str, successor: str) -> tester.Probe:
    return tester.Probe(name=name, kind="merged_module", version="13.0", model=name,
                        field="", detail="d", successor=successor)


def test_a_subject_that_was_never_there_is_not_reported_as_the_chain_behaving():
    """A real 12 -> 14 run reported two module probes as `gone as predicted`
    whose subjects had never been installed. Absent proves nothing on its own."""
    installed = _module_probe("account_coa_menu", "account_menu")
    never = _module_probe("base_vat_sanitized", "base_vat")
    rows = [["module", "account_menu", ""]]   # only the successor of the first
    states = {v.probe.name: v.state for v in tester.read_probe_states([installed, never], rows)}
    assert states["account_coa_menu"] == "gone as predicted"
    assert states["base_vat_sanitized"] == "not observed"


def test_not_observed_is_neither_a_finding_nor_counted_as_a_pass():
    verdicts = tester.read_probe_states([_module_probe("m", "s")], [])
    assert verdicts[0].state == "not observed" and not verdicts[0].is_finding
    # It sorts last, after everything that was actually measured — including the
    # passes. A probe that looked at nothing must not read as one that looked.
    mixed = tester.read_probe_states(
        [
            _module_probe("m", "s"),                       # not observed
            _probe("moved_field", field="kept"),           # intact
            _probe("removed_field", field="gone"),         # gone as predicted
        ],
        [["model", "sale.order", ""], ["field", "sale.order", "kept"]],
    )
    assert [v.state for v in mixed] == ["gone as predicted", "intact", "not observed"]


def test_the_state_query_asks_about_successors_too():
    sql = tester.probe_state_sql([_module_probe("old_mod", "new_mod")])
    assert "'new_mod'" in sql and "'old_mod'" in sql


def test_a_quiet_probe_is_not_blamed_for_what_a_later_step_did():
    """Six false alarms on a real 12 -> 19 run came from checking only at the end.

    A probe claims something about *its* step. `stock.quant/inventory_quantity`
    stops being computed at 15.0 and should survive that step; by 19.0 Odoo had
    removed it entirely, and the probe read that as a silent loss at 15.0.
    """
    probe = _probe("unfunction_field", field="inventory_quantity")   # declared for 16.0
    model = [["model", "sale.order", ""]]   # the owner is installed; the field is gone
    quiet = tester.read_probe_states([probe], model, at_version="16.0.1.0")
    assert quiet[0].state == "gone unannounced" and quiet[0].is_finding
    later = tester.read_probe_states([probe], model, at_version="19.0.1.3")
    assert later[0].state == "past its step" and not later[0].is_finding


def test_an_expected_removal_is_still_judged_from_any_later_version():
    # "It should be gone from its step onward" holds at every later version.
    probe = _probe("removed_field", field="auto_search")
    for version in ("16.0.1.0", "19.0.1.3"):
        assert tester.read_probe_states(
            [probe], [["model", "sale.order", ""]], at_version=version
        )[0].state == "gone as predicted"


def test_a_probe_whose_step_has_not_run_is_not_a_finding():
    """The mirror of `past its step`, and it matters when checking between steps:
    at 14.0, a probe about 18.0 says nothing — its subject is *supposed* to be
    there still."""
    probe = tester.Probe(name="p", kind="removed_field", version="18.0",
                         model="ir.cron", field="doall", detail="d")
    rows = [["model", "ir.cron", ""], ["field", "ir.cron", "doall"]]
    early = tester.read_probe_states([probe], rows, at_version="14.0.1.0")
    assert early[0].state == "not yet reached" and not early[0].is_finding
    at_its_step = tester.read_probe_states([probe], rows, at_version="18.0.1.3")
    assert at_its_step[0].state == "still there" and at_its_step[0].is_finding


def test_a_field_is_not_lost_from_a_model_the_database_never_had():
    """Four alarms at one step of a real run were about `stock.quant` and
    `purchase.order` in a database where neither module was installed."""
    probe = _probe("unfunction_field", model="stock.quant", field="inventory_quantity")
    # The model is absent: nothing was there to lose.
    absent = tester.read_probe_states([probe], [], at_version="16.0.1.0")
    assert absent[0].state == "not observed" and not absent[0].is_finding
    # The model is there and the field is not: that is the finding.
    present = tester.read_probe_states([probe], [["model", "stock.quant", ""]],
                                       at_version="16.0.1.0")
    assert present[0].state == "gone unannounced" and present[0].is_finding


def test_the_state_query_asks_about_the_model_of_a_field_subject():
    sql = tester.probe_state_sql([_probe("removed_field", model="sale.order", field="x")])
    assert "FROM ir_model WHERE model IN ('sale.order')" in sql
