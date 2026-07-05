"""Unit tests for pure planners — assert on the command plan, never execute it."""

from __future__ import annotations

from odoo_dwg import planners
from odoo_dwg.models import WorkspaceConfig


def _cfg(**kw) -> WorkspaceConfig:
    cfg = WorkspaceConfig(name="acme", versions=kw.pop("versions", ["18.0"]), **kw)
    cfg.normalize_defaults()
    return cfg


def test_write_text_file_command_is_heredoc_plus_chmod():
    cmds = planners.write_text_file_command("/tmp/x.conf", "hello\n", "640")
    assert len(cmds) == 2
    assert "cat > " in cmds[0].command and "<<'EOF'" in cmds[0].command
    assert cmds[1].command.startswith("chmod 640 ")


def test_repo_cache_clones_each_version_and_oca():
    cfg = _cfg(versions=["17.0", "18.0"], oca_repos=["web"])
    cmds = planners.plan_repo_cache(cfg)  # default exists = nothing present
    joined = "\n".join(c.command for c in cmds)
    assert "git clone --branch 17.0 --single-branch" in joined
    assert "git clone --branch 18.0 --single-branch" in joined
    assert "OCA/web.git" in joined
    # one odoo clone per version (2) + one OCA clone per version (2) = 4
    assert len(cmds) == 4


def test_repo_cache_skips_present_clone():
    cfg = _cfg(versions=["17.0", "18.0"])
    present = cfg.odoo_clone_dir("18.0")
    cmds = planners.plan_repo_cache(cfg, exists=lambda p: p == present)
    assert len(cmds) == 1  # only 17.0 remains
    assert str(present) not in "\n".join(c.command for c in cmds)


def test_workspace_tree_writes_files_but_builds_no_venv():
    cfg = _cfg(versions=["18.0"], oca_repos=["web"])
    cmds = planners.plan_workspace_tree(cfg)
    joined = "\n".join(c.command for c in cmds)
    assert "mkdir -p" in joined
    assert "ln -sfn" in joined  # OCA symlink
    assert "odoo18.conf" in joined
    assert "setup_venv.sh" in joined
    assert "README.md" in joined
    # The tree plan only creates dirs/symlinks and writes files — it must never
    # itself run a venv build, clone, or install (those belong to other plans).
    # (The setup_venv.sh it *writes* contains "python3 -m venv" as file content,
    # which is expected; here we check the executed command verbs.)
    allowed = {"mkdir", "ln", "cat", "chmod"}
    assert all(c.command.split()[0] in allowed for c in cmds)


def test_build_venv_creates_and_installs():
    cfg = _cfg(versions=["18.0"])
    cmds = planners.plan_build_venv(cfg, "18.0")
    joined = "\n".join(c.command for c in cmds)
    assert "python3 -m venv" in joined
    assert "requirements.txt" in joined
    assert "rm -rf" not in joined  # no recreate by default


def test_build_venv_recreate_removes_first():
    cfg = _cfg(versions=["18.0"])
    cmds = planners.plan_build_venv(cfg, "18.0", recreate=True)
    assert cmds[0].command.startswith("rm -rf ")


def _venv_builds(cmds) -> list:
    # A venv *build* command starts with the verb; the setup_venv.sh file we
    # write also contains that text as content, so match the executed verb only.
    return [c for c in cmds if c.command.startswith("python3 -m venv")]


def test_generate_workspace_composes_clone_tree_and_venvs():
    cfg = _cfg(versions=["17.0", "18.0"])
    cmds = planners.plan_generate_workspace(cfg)  # nothing present
    joined = "\n".join(c.command for c in cmds)
    assert "git clone --branch 17.0" in joined and "git clone --branch 18.0" in joined
    assert "workspace.json" in joined  # profile marker written by the tree
    assert len(_venv_builds(cmds)) == 2  # a venv build for each version


def test_generate_workspace_skips_present_venv():
    cfg = _cfg(versions=["17.0", "18.0"])
    present_venv = cfg.venv_dir("18.0")
    cmds = planners.plan_generate_workspace(cfg, exists=lambda p: p == present_venv)
    # 18.0 venv already present → only the 17.0 venv is built.
    assert len(_venv_builds(cmds)) == 1


def test_refresh_repos_pulls_present_clones_only():
    cfg = _cfg(versions=["17.0", "18.0"])
    present = cfg.odoo_clone_dir("18.0")
    cmds = planners.plan_refresh_repos(cfg, exists=lambda p: p == present)
    assert len(cmds) == 1
    assert cmds[0].command.startswith("git -C ") and "pull --ff-only" in cmds[0].command


# --- provisioning (F2) -----------------------------------------------------


def test_build_deps_plan_installs_key_packages():
    cmds = planners.plan_build_deps()
    joined = "\n".join(c.command for c in cmds)
    assert "apt-get update" in joined
    for pkg in ("build-essential", "libpq-dev", "libxml2-dev", "python3-venv"):
        assert pkg in joined


def test_postgresql_plan_installs_role_and_trust():
    cmds = planners.plan_postgresql("odoo")
    joined = "\n".join(c.command for c in cmds)
    assert "apt-get -y install postgresql" in joined
    assert "systemctl enable --now postgresql" in joined
    assert "CREATE ROLE odoo WITH LOGIN CREATEDB" in joined
    assert "IF NOT EXISTS" in joined  # idempotent
    assert "hba_file" in joined and "trust" in joined  # loopback trust


def test_wkhtmltopdf_version_rule():
    assert planners.wkhtmltopdf_target_version(14) == "0.12.5"
    assert planners.wkhtmltopdf_target_version(15) == "0.12.6"
    assert planners.wkhtmltopdf_target_version(18) == "0.12.6"


def test_wkhtmltopdf_asset_resolves_for_noble():
    asset = planners.resolve_wkhtmltopdf_asset("noble")
    assert asset is not None
    url, filename, sha = asset
    assert filename.endswith("_amd64.deb")
    assert len(sha) == 64
    assert planners.resolve_wkhtmltopdf_asset("unknown-codename") is None


def test_wkhtmltopdf_plan_verifies_checksum_for_odoo18():
    cmds = planners.plan_wkhtmltopdf(18, "noble")
    joined = "\n".join(c.command for c in cmds)
    assert "curl -fSL" in joined
    assert "sha256sum -c -" in joined  # abort on mismatch
    assert "apt-get -y install" in joined


def test_wkhtmltopdf_plan_empty_for_legacy_and_unmapped():
    assert planners.plan_wkhtmltopdf(14, "noble") == []  # 0.12.5 not pinned → distro/skip
    assert planners.plan_wkhtmltopdf(18, "unknown") == []  # unmapped codename → no guessed URL


def test_node_rtlcss_plan():
    joined = "\n".join(c.command for c in planners.plan_node_rtlcss())
    assert "nodejs" in joined and "npm install -g rtlcss" in joined
