"""Migration mode — OpenUpgrade chained upgrade 12→19.

Emits a per-version clone + venv (interpreter matched via ``uv``) + per-step
``odoo.conf`` and a checkpointing ``run_migration.sh`` driver, with an optional
Docker fallback for the versions whose Python is impractical natively (12/13).
F0 stub: navigable menu only. F3 implements the pipeline (see docs/migration).
"""

from __future__ import annotations

from ..i18n import t
from ..ui import level_text


def migration_menu() -> None:
    print(level_text("INFO", t("(not implemented yet)")))
