"""Suite-wide guards: no test reads the host it runs on."""

from __future__ import annotations

import pytest

from odoo_dwg import system


@pytest.fixture(autouse=True)
def _no_host_clusters(monkeypatch):
    """The local cluster's port comes from ``pg_lsclusters``; a test never asks the
    host, so every default port is PostgreSQL's own unless a test says otherwise."""
    monkeypatch.setattr(system, "_clusters", lambda: None)
