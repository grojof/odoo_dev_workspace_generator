"""Unit tests for the domain model — pure, no filesystem or shell access."""

from __future__ import annotations

import json

import pytest

from odoo_dwg.models import (
    MIGRATION_CHAIN,
    InstanceConfig,
    WorkspaceConfig,
    odoo_major,
    python_minimum_for,
)


def test_odoo_major_parses_version():
    assert odoo_major("18.0") == 18
    assert odoo_major("12.0") == 12
    with pytest.raises(ValueError):
        odoo_major("not-a-version")


def test_python_minimum_matches_official_floors():
    # Verbatim from the official "Source install" pages.
    assert python_minimum_for("12.0") == "3.5"
    assert python_minimum_for("13.0") == "3.6"
    assert python_minimum_for("14.0") == "3.7"
    assert python_minimum_for("17.0") == "3.10"
    assert python_minimum_for("18.0") == "3.10"


def test_migration_chain_is_sequential_no_skips():
    majors = [odoo_major(v) for v in MIGRATION_CHAIN]
    assert majors == list(range(12, 20))


def test_instance_names_and_paths():
    inst = InstanceConfig("acme", "18.0")
    assert inst.name == "odoo18acme"
    assert inst.venv_name == "odoo18"
    assert inst.conf_name == "odoo18.conf"
    assert inst.python_minimum == "3.10"


def test_workspace_port_offsets_are_deterministic():
    cfg = WorkspaceConfig(name="acme", versions=["18.0", "17.0", "19.0"])
    cfg.normalize_defaults()
    # Sorted by major → 17=base, 18=+10, 19=+20.
    assert cfg.http_port_for("17.0") == 8069
    assert cfg.http_port_for("18.0") == 8079
    assert cfg.http_port_for("19.0") == 8089


def test_normalize_defaults_fills_user_and_prefix():
    cfg = WorkspaceConfig(name="acme")
    cfg.normalize_defaults()
    assert cfg.db_user == "acme"
    assert cfg.addon_prefix == "acme"


def test_validate_rejects_bad_name_and_version():
    with pytest.raises(ValueError):
        cfg = WorkspaceConfig(name="Acme!", versions=["18.0"])
        cfg.validate()
    with pytest.raises(ValueError):
        cfg = WorkspaceConfig(name="acme", versions=["nope"])
        cfg.validate()


def test_json_round_trip_ignores_unknown_keys():
    cfg = WorkspaceConfig(name="acme", versions=["18.0"])
    cfg.normalize_defaults()
    data = json.loads(cfg.to_json())
    data["some_future_key"] = "ignored"
    restored = WorkspaceConfig.from_dict(data)
    assert restored.name == "acme"
    assert restored.versions == ["18.0"]
