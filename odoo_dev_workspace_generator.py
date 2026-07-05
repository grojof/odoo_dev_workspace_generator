#!/usr/bin/env python3
"""Thin root entry point (mirrors ``odoo_instance_manager.py``).

Lets the tool run as a single script (``python3 odoo_dev_workspace_generator.py``)
as well as a module (``python3 -m odoo_dwg``) or the installed console script
(``odoo-dwg``).
"""

from __future__ import annotations

from odoo_dwg.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
