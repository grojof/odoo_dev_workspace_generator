"""User-facing workflows: the two sections (provision, workspace) and the
migration mode. Each function owns its menu, plan assembly, and discovery, over
the shared primitives in ``system``/``prompts``/``ui``.

F0 ships thin, honest stubs so the menu and CLI are navigable end to end; the
real capabilities land in F1 (workspace), F2 (provision), and F3 (migration).
"""

from __future__ import annotations

from .migration import migration_menu
from .provision import provision_menu
from .workspace import workspace_menu

__all__ = ["migration_menu", "provision_menu", "workspace_menu"]
