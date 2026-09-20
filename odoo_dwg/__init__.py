"""odoo_dwg — Odoo development & migration workspace generator.

A zero-runtime-dependency (standard-library-only) tool that *generates and
maintains* Odoo Community development workspaces and migration environments on a
Linux host (WSL Ubuntu 24.04, a server, or a container — the host is the user's
choice). It never guesses: every host-mutating action assembles a command
**plan**, previews it, and applies it only after confirmation.

The package mirrors the layered structure of its sibling app
``odoo_instance_manager``: pure ``planners`` build ``Command`` lists, ``system``
executes them, ``ui``/``prompts`` handle the terminal, and ``workflows`` wires
the two user-facing sections (``provision``, ``workspace``) plus the
``migration`` mode.
"""

from __future__ import annotations

__version__ = "0.2.0"
