"""Unit tests for pure planners — assert on the command plan, never execute it."""

from __future__ import annotations

from odoo_dwg import planners
from odoo_dwg.models import WorkspaceConfig, resolve_interpreter


def _cfg(**kw) -> WorkspaceConfig:
    cfg = WorkspaceConfig(name="acme", versions=kw.pop("versions", ["18.0"]), **kw)
    cfg.normalize_defaults()
    return cfg


def test_write_text_file_command_is_heredoc_plus_chmod():
    cmds = planners.write_text_file_command("/tmp/x.conf", "hello\n", "640")
    assert len(cmds) == 2
    assert "cat > " in cmds[0].command and "<<'EOF'" in cmds[0].command
    assert cmds[1].command.startswith("chmod 640 ")


def test_heredoc_delimiter_never_matches_a_content_line():
    assert planners.heredoc_delimiter("hello\n") == "EOF"
    # A line equal to the delimiter would end the heredoc and run what follows.
    assert planners.heredoc_delimiter("a\nEOF\nEOF_\n") == "EOF__"
    # Only whole lines matter: EOF inside a line cannot close the heredoc.
    assert planners.heredoc_delimiter("x EOF y\nEOFx\n") == "EOF"


def test_write_text_file_command_contains_hostile_content():
    # A profile value carrying a newline and the default delimiter, as a
    # hand-edited workspace.json could.
    content = "db_host = 127.0.0.1\nEOF\nrm -rf ~\n"
    command = planners.write_text_file_command("/tmp/x.conf", content)[0].command
    header, _, rest = command.partition("\n")
    delimiter = header.split("<<")[1].strip("'")
    body_lines = rest.split("\n")
    # The heredoc ends only at its final line, so every content line is data.
    assert body_lines[-1] == delimiter
    assert delimiter not in body_lines[:-1]
    assert "\n".join(body_lines[:-1]) + "\n" == content  # exactly the content, no extra line


def test_repo_cache_clones_each_version_and_oca():
    cfg = _cfg(versions=["17.0", "18.0"], oca_repos=["web"])
    cmds = planners.plan_repo_cache(cfg)  # default exists = nothing present
    joined = "\n".join(c.command for c in cmds)
    assert "git clone --depth 1 --branch 17.0 --single-branch" in joined
    assert "git clone --depth 1 --branch 18.0 --single-branch" in joined
    assert "OCA/web.git" in joined
    # one odoo clone per version (2) + one OCA clone per version (2) = 4
    assert len(cmds) == 4
    # Every clone is shallow, OCA included: history is most of a clone's size.
    assert all("--depth 1 " in c.command for c in cmds)


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


def test_build_venv_uses_uv_for_an_out_of_range_interpreter():
    # Odoo 14 tops out at 3.10, so a 3.12 host resolves to a uv-provided 3.8.
    cfg = _cfg(versions=["14.0"])
    choice = resolve_interpreter("14.0", host_python="3.12")
    cmds = planners.plan_build_venv(cfg, "14.0", interpreter=choice)
    create = cmds[0].command
    assert create.startswith("uv venv --seed --no-project --python 3.8 ")
    assert "python3 -m venv" not in "\n".join(c.command for c in cmds)
    # --seed puts pip in the venv, so the install steps stay unchanged.
    assert any("/bin/pip install -r " in c.command for c in cmds)


def test_build_venv_keeps_plain_python3_for_an_in_range_interpreter():
    cfg = _cfg(versions=["18.0"])
    choice = resolve_interpreter("18.0", host_python="3.12")
    cmds = planners.plan_build_venv(cfg, "18.0", interpreter=choice)
    assert cmds[0].command.startswith("python3 -m venv ")
    assert "uv venv" not in "\n".join(c.command for c in cmds)


def test_generate_workspace_applies_per_version_interpreters():
    cfg = _cfg(versions=["14.0", "18.0"])
    interpreters = {
        version: resolve_interpreter(version, host_python="3.12") for version in cfg.versions
    }
    cmds = planners.plan_generate_workspace(cfg, interpreters=interpreters)
    joined = "\n".join(c.command for c in cmds)
    # One venv per version, each with the interpreter resolved for it.
    assert "uv venv --seed --no-project --python 3.8 " in joined
    assert "python3 -m venv " in joined


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
    assert "git clone --depth 1 --branch 17.0" in joined
    assert "git clone --depth 1 --branch 18.0" in joined
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
    assert "apt-get -y install --no-install-recommends nodejs npm" in joined


def test_build_venv_pins_setuptools_per_era():
    # <=13: vatnumber's setup.py needs use_2to3 (setuptools<58); 14-16 import
    # pkg_resources at startup (setuptools<81); 17+ need neither.
    expected = {
        "12.0": "'setuptools<58'",
        "13.0": "'setuptools<58'",
        "14.0": "'setuptools<81'",
        "15.0": "'setuptools<81'",
        "16.0": "'setuptools<81'",
        "17.0": "setuptools",
        "19.0": "setuptools",
    }
    for version, requirement in expected.items():
        upgrade = planners.plan_build_venv(_cfg(versions=[version]), version)[1].command
        assert upgrade.endswith(f"install --upgrade pip wheel {requirement}"), upgrade


def test_odoo_12_installs_python_ldap_instead_of_the_deprecated_pyldap():
    install = planners.plan_build_venv(_cfg(versions=["12.0"]), "12.0")[2].command
    assert install.startswith("grep -v -i -E '^pyldap([=<>!~; ]|$)' ")
    assert install.endswith("install -r /dev/stdin python-ldap==3.1.0")
    # Other versions install their requirements untouched.
    other = planners.plan_build_venv(_cfg(versions=["13.0"]), "13.0")[2].command
    assert "grep" not in other and other.endswith("/odoo-13.0/requirements.txt")


# --- refreshing an existing workspace ---------------------------------------


def _generated(cfg, interpreters=None) -> dict:
    return {path: content for path, content, _mode in planners.generated_files(cfg, interpreters)}


def test_tree_writes_exactly_the_generated_files():
    cfg = _cfg(versions=["18.0"])
    written = [c.command for c in planners.plan_workspace_tree(cfg) if c.command.startswith("cat > ")]
    assert len(written) == len(planners.generated_files(cfg))


def test_refresh_is_empty_when_everything_is_current():
    cfg = _cfg(versions=["18.0"])
    current = _generated(cfg)
    assert planners.plan_refresh_files(cfg, None, current.get) == []


def test_refresh_backs_up_and_rewrites_only_what_changed():
    cfg = _cfg(versions=["18.0"])
    current = _generated(cfg)
    launch = cfg.vscode_dir / "launch.json"
    current[launch] = '{"configurations": []}\n'  # an older generator's file
    cmds = [c.command for c in planners.plan_refresh_files(cfg, None, current.get)]
    assert cmds[0] == f"cp -p {launch} {launch}.bak"
    assert cmds[1].startswith(f"cat > {launch} <<")
    assert cmds[2].startswith("chmod 644 ")
    assert len(cmds) == 3  # nothing else is touched


def test_refresh_creates_a_missing_file_without_a_backup():
    cfg = _cfg(versions=["18.0"])
    current = _generated(cfg)
    del current[cfg.odools_file]
    cmds = [c.command for c in planners.plan_refresh_files(cfg, None, current.get)]
    assert cmds[0] == f"mkdir -p {cfg.odools_file.parent}"
    assert not any(c.startswith("cp -p") for c in cmds)


def test_refresh_never_touches_addons_venvs_or_clones():
    cfg = _cfg(versions=["18.0"], oca_repos=["web"])
    cmds = planners.plan_refresh_files(cfg, None, lambda _path: None)
    # Only these verbs run; file contents (which mention git, pip, rm) are data.
    for c in cmds:
        assert c.command.split()[0] in {"mkdir", "cp", "cat", "chmod"}


def test_refresh_ignores_a_trailing_blank_line_from_older_writes():
    cfg = _cfg(versions=["18.0"])
    current = {path: text + "\n" for path, text in _generated(cfg).items()}
    assert planners.plan_refresh_files(cfg, None, current.get) == []
