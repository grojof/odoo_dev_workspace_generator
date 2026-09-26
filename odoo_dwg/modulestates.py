"""Modules left "to install" with no code, cancelled after the target step.

OpenUpgrade 18.0 patches ``update_list`` (``openupgrade_framework/odoo_patch/odoo/addons/base/models/
ir_module.py``) to mark "to install" every uninstalled auto-install module whose recorded dependencies
are installed, whether or not its code still exists. Dependencies merged or renamed along the chain make
old auto-install modules look satisfied. Odoo skips them as not installable and ends the step with "Some
modules have inconsistent states"; left as they are, every later module operation repeats it, and the
Apps screen shows installs that can never happen.

After the target step, the target's own Odoo cancels the pending install of each such module whose code
it cannot find (``get_module_path``), with ``button_install_cancel``, as the Apps screen does. A pending
install whose code exists is left for the operator, and listed.

Pure: this module holds the shell script; the migration driver runs it.
"""

from __future__ import annotations

#: The version whose framework marks codeless auto-install modules "to install".
FROM_STEP = 18


def applies(source_major: int, target_major: int) -> bool:
    return source_major < FROM_STEP <= target_major


#: Run by the target's ``odoo-bin shell``. Appends ``kind<TAB>module<TAB>detail`` to
#: ``$ODWG_MODULE_STATES_LIST``.
CANCEL = """\
import os
from odoo.modules.module import get_module_path
Module = env["ir.module.module"].sudo()
pending = Module.search([("state", "=", "to install")])
codeless = pending.filtered(lambda m: not get_module_path(m.name, display_warning=False))
codeless.button_install_cancel()
env.cr.commit()
with open(os.environ["ODWG_MODULE_STATES_LIST"], "a", encoding="utf-8") as out:
    for module in codeless:
        out.write("install-cancelled\\t%s\\tno code on the addons path\\n" % module.name)
    for module in pending - codeless:
        out.write("install-pending\\t%s\\tits code exists: install or cancel it\\n" % module.name)
print("[repair] module states: %d pending install(s) with no code cancelled, %d left pending"
      % (len(codeless), len(pending - codeless)))
"""
