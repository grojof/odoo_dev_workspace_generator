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
