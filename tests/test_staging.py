"""Unit tests for custom-module staging — analysis parser/scanner, planners,
scaffold and report templates. Fixture format mirrors the real
``upgrade_analysis.txt`` of OpenUpgrade 18.0 (base module)."""

from __future__ import annotations

import ast

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
    assert "partner_share_token" in text and "'views/view.xml':12" in text
    assert "pass  # TODO" in text  # does nothing until completed


def test_a_file_name_cannot_write_code_into_the_scaffold():
    """The path comes from the operator's module tree, and OpenUpgrade *executes*
    this file: a newline in a file name must not end the comment it sits in."""
    evil = "models.py\nimport os; os.system('id')\n#x.py"
    finding = Finding(evil, 4,
                      AnalysisRecord("base", "res.partner", "removed_field", "old_field"))
    text = templates.render_migration_scaffold("client_sales", "18.0", [finding])
    statements = [type(node).__name__ for node in ast.parse(text).body]
    assert statements == ["ImportFrom", "FunctionDef"]
    assert "\\n" in text  # the newline is shown, escaped, not acted on


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


def test_the_scan_still_reads_names_the_way_the_regexes_did():
    """The scan looks names up now instead of searching for each one. The two
    boundary rules it replaced: a field matches inside a dotted name, a model
    only as a whole one."""
    records = [
        AnalysisRecord("base", "res.partner", "removed_field", "token"),
        AnalysisRecord("base", "res.partner", "removed_model", "res.partner"),
        # Dotted field names do not occur in real analysis files, but the rule
        # they fall under is the same one, and a fuzz against the old regexes
        # found this the only place the two readings could part.
        AnalysisRecord("base", "res.partner", "removed_field", "partner.bank"),
    ]
    files = [("m.py", "x = res.partner.token\ny = res.partner.bank.iban\nz = 'tokens'\n")]
    hits = {(f.record.name, f.line) for f in analysis.scan_source(files, records)}
    assert ("token", 1) in hits              # inside a dotted name
    assert ("res.partner", 1) not in hits    # not inside a longer one
    assert ("partner.bank", 2) in hits       # a dotted field, still bounded
    assert ("token", 3) not in hits          # `tokens` is another word


def test_the_legacy_fork_names_its_analysis_files_differently(tmp_path, monkeypatch):
    """Up to 13.0 OpenUpgrade embeds the analysis in each add-on's `migrations/`
    directory and calls it `openupgrade_analysis.txt`; from 14.0 it lives under
    `openupgrade_scripts/` as `upgrade_analysis.txt`.

    Reading only the newer name found nothing in the 12 → 13 step — against a
    real clone, 0 records where there are 512 — and staging then reported no
    candidate findings, which reads exactly like having none.
    """
    from odoo_dwg.workflows import migration

    monkeypatch.setattr(MigrationEnv, "base_dir", str(tmp_path))
    env = MigrationEnv(source="12.0", target="14.0")

    legacy = env.openupgrade_clone_dir("13.0") / "addons" / "sale" / "migrations" / "13.0.1.0"
    legacy.mkdir(parents=True)
    (legacy / "openupgrade_analysis.txt").write_text(ANALYSIS_FIXTURE, encoding="utf-8")
    # The work file the tool writes beside it is not a source of record.
    (legacy / "openupgrade_analysis_work.txt").write_text(
        "---Models in module 'sale'---\nobsolete model never.read\n", encoding="utf-8"
    )

    modern = env.openupgrade_clone_dir("14.0") / "openupgrade_scripts" / "scripts" / "sale" / "14.0.1.0"
    modern.mkdir(parents=True)
    (modern / "upgrade_analysis.txt").write_text(ANALYSIS_FIXTURE, encoding="utf-8")

    for version in ("13.0", "14.0"):
        names = {record.name for record in migration._step_analysis_records(env, version)}
        assert "ir.property" in names and "doall" in names, version
        assert "never.read" not in names, version


# --- carrying the work forward ------------------------------------------------


def _promoted(tmp_path):
    from odoo_dwg.models import PromotedModules
    return PromotedModules(base_dir=str(tmp_path / "kept"))


def test_reviewed_code_is_promoted_by_copying_and_without_its_throwaway_repo(tmp_path):
    """The environment must stay runnable after a promotion, and the git repo the
    migrator needs inside a stage directory is not the operator's history."""
    env = MigrationEnv(source="12.0", target="14.0")
    kept = _promoted(tmp_path)
    commands = planners.plan_promote_module(env, "client_sales", ["13.0", "14.0"], kept)

    assert len(commands) == 2
    for version, command in zip(("13.0", "14.0"), commands, strict=True):
        text = command.command
        source = str(env.addons_custom_dir(version) / "client_sales")
        assert f"cp -a {source} " in text            # copied
        assert f"rm -rf {source}" not in text        # never moved
        assert str(kept.module_dir(version, "client_sales")) in text
        assert text.endswith("/.git")                # the throwaway repo stays behind


def test_a_promoted_step_is_taken_as_given_and_runs_no_migrator(tmp_path):
    """The final run applies proven work instead of deriving it a second time."""
    env = MigrationEnv(source="12.0", target="15.0")
    kept = _promoted(tmp_path)
    have = {kept.module_dir(v, "m") for v in ("13.0", "14.0")}

    nothing = planners.plan_stage_module(env, "m", tmp_path / "src")
    assert sum("odoo-module-migrate" in c.command for c in nothing) == 3

    partly = planners.plan_stage_module(
        env, "m", tmp_path / "src", promoted=kept, exists=lambda p: p in have
    )
    assert sum("odoo-module-migrate" in c.command for c in partly) == 1
    assert sum("from the promoted copy" in c.description for c in partly) == 2
    # And 15.0 still derives from 14.0's staged directory, which promotion filled.
    derived = next(c for c in partly if "odoo-module-migrate" in c.command)
    assert "--target-version-name 15.0" in derived.command


def test_divergence_is_decided_by_content_not_by_timestamps(tmp_path, monkeypatch):
    from odoo_dwg import preflight

    monkeypatch.setattr(MigrationEnv, "base_dir", str(tmp_path / "envs"))
    env = MigrationEnv(source="12.0", target="14.0")
    kept = _promoted(tmp_path)

    def put(root, text):
        root.mkdir(parents=True, exist_ok=True)
        (root / "m.py").write_text(text, encoding="utf-8")

    put(env.addons_custom_dir("13.0") / "m", "reviewed")
    put(kept.module_dir("13.0", "m"), "reviewed")
    # The repo the migrator needs is scaffolding, not the module.
    (env.addons_custom_dir("13.0") / "m" / ".git").mkdir()
    (env.addons_custom_dir("13.0") / "m" / ".git" / "HEAD").write_text("ref: x")
    # Same content, different times: not divergence.
    import os
    os.utime(env.addons_custom_dir("13.0") / "m" / "m.py", (0, 0))

    put(env.addons_custom_dir("14.0") / "m", "kept working on it")
    put(kept.module_dir("14.0", "m"), "as promoted")

    assert preflight.divergence(env, "m", kept, ["13.0", "14.0"]) == [
        ("13.0", "same"),
        ("14.0", "diverged"),
    ]


def test_the_report_names_divergence_without_choosing_a_winner():
    report = templates.render_staging_report(
        "client_sales", [("14.0", "", [], None)], promoted=[("13.0", "same"), ("14.0", "diverged")]
    )
    assert "| 14.0 | diverged |" in report
    assert "Neither is authoritative" in report
