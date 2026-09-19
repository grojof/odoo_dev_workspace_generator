"""User-facing workflows: the two sections (provision, workspace) and the
migration mode. Each function owns its menu, plan assembly, and discovery, over
the shared primitives in ``system``/``prompts``/``ui``.

``common`` holds what more than one menu uses: applying a previewed plan, and
redirecting a rehearsal database's mail to the local capture.
"""

from __future__ import annotations

from .migration import migration_menu
from .provision import provision_menu
from .workspace import workspace_menu

__all__ = ["migration_menu", "provision_menu", "workspace_menu"]
