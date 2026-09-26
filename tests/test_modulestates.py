"""Pending installs with no code: cancelled after the target step with Odoo's own methods."""

from __future__ import annotations

from odoo_dwg import modulestates, templates
from odoo_dwg.models import MigrationEnv


def test_it_applies_to_a_chain_that_crosses_18():
    assert modulestates.applies(12, 18) and not modulestates.applies(18, 19)
    assert not modulestates.applies(12, 17)


def test_only_modules_whose_code_odoo_cannot_find_are_cancelled():
    script = modulestates.CANCEL
    compile(script, "cancel", "exec")
    assert 'Module.search([("state", "=", "to install")])' in script
    assert "not get_module_path(m.name, display_warning=False)" in script
    assert "codeless.button_install_cancel()" in script
    assert "install-pending" in script


def test_the_target_step_cancels_them_last_before_its_checkpoint():
    sh = templates.render_run_migration_sh(MigrationEnv(source="12.0", target="18.0"))
    order = [sh.index(marker) for marker in (
        'mark "18.0" repair source-configuration', "<<'ODWG_MODSTATES'",
        'mark "18.0" repair module-states', 'checkpoint "18.0"', "# --- stage: the client's modules")]
    assert order == sorted(order)
