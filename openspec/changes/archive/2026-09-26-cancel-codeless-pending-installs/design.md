# Design

The module's code is found with Odoo's own `odoo.modules.module.get_module_path`: the step's addons
path, exactly as Odoo reads it. The cancel is `ir.module.module.button_install_cancel`, which sets the
state to `uninstalled`. The step runs last before the checkpoint, so the client-modules stage finds no
pending install it did not ask for. A pending install whose code exists is not cancelled: installing it
may be what the chain meant.
