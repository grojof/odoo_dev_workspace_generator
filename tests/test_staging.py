"""Unit tests for custom-module staging — analysis parser/scanner, planners,
scaffold and report templates. Fixture format mirrors the real
``upgrade_analysis.txt`` of OpenUpgrade 18.0 (base module)."""

from __future__ import annotations

from odoo_dwg import analysis, planners, templates
from odoo_dwg.analysis import AnalysisRecord, Finding
from odoo_dwg.models import MigrationEnv

ANALYSIS_FIXTURE = """\
---Models in module 'base'---
obsolete model ir.property
new model ir.embedded.actions
---Fields in module 'base'---
base         / ir.cron                  / doall (boolean)               : DEL
base         / ir.cron                  / failure_count (integer)       : NEW hasdefault: default
base         / ir.cron                  / interval_number (integer)     : now required
base         / res.partner              / partner_share_token (char)    : DEL
"""


def test_parse_analysis_extracts_only_breaking_records():
    records = analysis.parse_analysis(ANALYSIS_FIXTURE)
    kinds = {(r.kind, r.name) for r in records}
    assert ("removed_model", "ir.property") in kinds
    assert ("removed_field", "doall") in kinds
    assert ("removed_field", "partner_share_token") in kinds
    assert not any(r.name == "failure_count" for r in records)      # NEW ignored
    assert not any(r.name == "interval_number" for r in records)    # 'now required' ignored


def test_scan_requires_model_co_occurrence_for_fields():
    records = analysis.parse_analysis(ANALYSIS_FIXTURE)
    with_model = [("models/cron.py", "cron = env['ir.cron']\nif cron.doall:\n    pass")]
    without_model = [("models/other.py", "doall = True")]
    assert any(f.record.name == "doall" for f in analysis.scan_source(with_model, records))
    assert not analysis.scan_source(without_model, records)


def test_scan_skips_generic_field_names():
    records = [AnalysisRecord("base", "ir.property", "removed_field", "name")]
    files = [("models/p.py", "x = env['ir.property'].name")]
    assert analysis.scan_source(files, records) == []


def test_scan_matches_removed_model_with_line_numbers():
    records = analysis.parse_analysis(ANALYSIS_FIXTURE)
    files = [("models/legacy.py", "# uses properties\nprops = env['ir.property'].search([])")]
    findings = [f for f in analysis.scan_source(files, records) if f.record.kind == "removed_model"]
    assert findings and findings[0].line == 2 and findings[0].path == "models/legacy.py"


def test_stage_module_plan_is_stepwise_and_never_touches_the_source():
    env = MigrationEnv(source="15.0", target="17.0")
    cmds = planners.plan_stage_module(env, "client_sales", env.root / "src")
    joined = "\n".join(c.command for c in cmds)
    # Step 1 copies from the operator source; step 2 from the previous stage.
    src_copy = joined.index("rm -rf")
    assert str(env.addons_custom_dir("16.0")) in joined
    assert joined.index("--init-version-name 15.0") < joined.index("--init-version-name 16.0")
    assert "--target-version-name 16.0" in joined and "--target-version-name 17.0" in joined
    assert src_copy >= 0
    # The source dir is only ever read (cp -a FROM it), never an rm/mv target.
    for c in cmds:
        if c.command.startswith("rm -rf"):
            assert str(env.root / "src") not in c.command.split("&&")[0]
    # Tool output is captured per step, with pipefail so failures still fail.
    assert "set -o pipefail" in joined and "tee" in joined
    # The tool needs a git repo (verified on WSL) — each stage dir gets one.
    assert "git" in joined and "init -q" in joined and "commit -qm" in joined


def test_staging_tool_plan_uses_the_shared_uv_venv():
    env = MigrationEnv(source="15.0", target="16.0")
    cmds = planners.plan_staging_tool(env)
    joined = "\n".join(c.command for c in cmds)
    assert str(env.staging_tool_venv) in joined
    assert "uv venv --clear --no-project" in joined
    assert "odoo-module-migrator" in joined


def test_scaffold_is_inert_and_lists_findings():
    finding = Finding("views/view.xml", 12,
                      AnalysisRecord("base", "res.partner", "removed_field", "partner_share_token"))
    text = templates.render_migration_scaffold("client_sales", "17.0", [finding])
    assert "REVIEW REQUIRED" in text
    assert "from openupgradelib import openupgrade" in text
    assert "partner_share_token" in text and "views/view.xml:12" in text
    assert "pass  # TODO" in text  # does nothing until completed


def test_report_carries_tool_log_verbatim_and_states_the_boundary():
    finding = Finding("models/m.py", 3,
                      AnalysisRecord("base", "ir.cron", "removed_field", "doall"))
    report = templates.render_staging_report(
        "client_sales",
        [("16.0", "19:37:55 WARNING Replaced dependency", [finding], "migrations/16.0.1.0.0/pre-migration.py"),
         ("17.0", "", [], None)],
    )
    assert "19:37:55 WARNING Replaced dependency" in report      # verbatim
    assert "your review" in report and "completes the migration" in report
    assert "`ir.cron` field `doall`" in report
    assert "Scaffold written" in report
    assert "## Step 17.0" in report and "None detected." in report
