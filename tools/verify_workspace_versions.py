#!/usr/bin/env python3
"""Build a throwaway workspace with every Odoo version and prove each one runs.

Developer tooling, not part of the package: ``odoo_dwg`` never imports this. Unit
tests prove the *plan*; only a real host proves a venv builds and Odoo starts. Run
it on the reference host whenever what a venv installs may have moved:

    python tools/verify_workspace_versions.py              # every supported version
    python tools/verify_workspace_versions.py 12.0 15.0    # only these
    python tools/verify_workspace_versions.py --keep       # leave everything for inspection

What it does, in order (see docs/workspace-layout.md for when and how to act on it):

1. Generates a workspace named ``verifyall`` with the requested versions through
   the tool's own plan (``plan_generate_workspace``), each version on the
   interpreter the tool picks by default for this host. The plan is previewed and
   applied only after you type ``yes`` (or pass ``--yes``).
2. For each version reports the venv's Python and setuptools, installs ``base``
   and ``barcodes`` (a small module with tests in every version) with demo data
   into a fresh database ``verifyall_<major>``, then runs the workspace's own debug
   configurations from the generated ``.vscode/launch.json``, with the prompts
   answered: the **shell** must evaluate an ORM query piped into it, **test
   module** must run ``barcodes``' tests without failures, and **upgrade
   modules** must serve ``/web/login`` with the login form.
3. Removes what it created — the workspace, its databases and filestores, and
   only the shared clones that did not exist before — unless ``--keep``.

Needs network, PostgreSQL with the development role (``provision apply``) and
``uv``. Exits 0 when every version passes, 1 otherwise. It never edits the tool.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from odoo_dwg import planners, system  # noqa: E402
from odoo_dwg.models import (  # noqa: E402
    ODOO_SUPPORT,
    WorkspaceConfig,
    odoo_major,
    resolve_interpreter,
)
from odoo_dwg.ui import render_table  # noqa: E402

NAME = "verifyall"
SERVE_TIMEOUT = 120
TEST_MODULE = "barcodes"
SHELL_PROBE = "print('ORM_OK', env['res.users'].search_count([]))\n"
# Odoo's default data_dir; the generated odoo.conf does not override it.
FILESTORE = Path("~/.local/share/Odoo/filestore").expanduser()


def _database(version: str) -> str:
    return f"{NAME}_{odoo_major(version)}"


def _psql(cfg: WorkspaceConfig, sql: str) -> str:
    result = subprocess.run(
        ["psql", "-h", cfg.db_host, "-p", str(cfg.db_port), "-U", cfg.db_user,
         "-d", "postgres", "-tAc", sql],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip()


def _refuse_if_present(cfg: WorkspaceConfig) -> str | None:
    if cfg.root.exists():
        return f"{cfg.root} already exists — remove it or run with it gone."
    names = ", ".join(f"'{_database(v)}'" for v in cfg.versions)
    taken = _psql(cfg, f"select datname from pg_database where datname in ({names})")
    if taken:
        return f"databases already exist: {taken.split()}"
    return None


def _odoo_bin(cfg: WorkspaceConfig, version: str, *args: str) -> list[str]:
    return [
        str(cfg.venv_dir(version) / "bin" / "python"),
        str(cfg.odoo_clone_dir(version) / "odoo-bin"),
        "-c", str(cfg.config_file(version)),
        *args,
    ]


def _venv_facts(cfg: WorkspaceConfig, version: str) -> str:
    python = cfg.venv_dir(version) / "bin" / "python"
    if not python.exists():
        return "no venv"
    probe = "import sys, setuptools; print(sys.version.split()[0], setuptools.__version__)"
    result = subprocess.run([str(python), "-c", probe], capture_output=True, text=True)
    return result.stdout.strip() or result.stderr.strip().splitlines()[-1]


def _launch_commands(cfg: WorkspaceConfig, version: str, database: str) -> dict[str, list[str]]:
    """The generated debug configurations for ``version``, keyed by kind, as the
    command debugpy would run once VS Code has asked its prompts."""
    answers = {
        "${input:odooDatabase}": database,
        "${input:odooModules}": TEST_MODULE,
        "${input:odooTestModule}": TEST_MODULE,
    }
    launch = json.loads((cfg.vscode_dir / "launch.json").read_text(encoding="utf-8"))
    commands: dict[str, list[str]] = {}
    for configuration in launch["configurations"]:
        if not configuration["python"].endswith(f"/odoo{odoo_major(version)}/bin/python"):
            continue
        kind = next(
            (k for k in ("shell", "upgrade modules", "test module") if f" {k} (" in configuration["name"]),
            "serve",
        )
        args = []
        for arg in configuration["args"]:
            for placeholder, answer in answers.items():
                arg = arg.replace(placeholder, answer)
            args.append(arg)
        commands[kind] = [configuration["python"], configuration["program"], *args]
    return commands


def _shell_answers(command: list[str]) -> str:
    result = subprocess.run(command, input=SHELL_PROBE, capture_output=True, text=True, timeout=300)
    return "ORM ok" if "ORM_OK" in result.stdout else f"no answer (exit {result.returncode})"


def _tests_pass(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
    log = result.stdout + result.stderr
    ran = f"odoo.addons.{TEST_MODULE}.tests" in log
    problems = len(re.findall(r" (ERROR|CRITICAL) |FAIL:", log))
    if result.returncode == 0 and ran and problems == 0:
        return "tests ok"
    return f"exit {result.returncode}, ran={ran}, {problems} problems"


def _serves_login(cfg: WorkspaceConfig, version: str, database: str, command: list[str]) -> str:
    url = f"http://127.0.0.1:{cfg.http_port_for(version)}/web/login?db={database}"
    server = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + SERVE_TIMEOUT
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=5) as response:
                    page = response.read().decode("utf-8", "replace")
                return "login form" if 'name="login"' in page else "200 without form"
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(2)
        return "no answer"
    finally:
        server.terminate()
        server.wait(timeout=30)


def _check(cfg: WorkspaceConfig, version: str) -> tuple[bool, list[str]]:
    database = _database(version)
    facts = _venv_facts(cfg, version)
    init = subprocess.run(
        # With demo data: Odoo 12 only runs tests on a demo database
        # (odoo/modules/loading.py: "launch tests only in demo mode").
        _odoo_bin(cfg, version, "-d", database, "-i", f"base,{TEST_MODULE}", "--stop-after-init"),
        capture_output=True, text=True,
    )
    errors = len(re.findall(r" (ERROR|CRITICAL) ", init.stdout + init.stderr))
    if init.returncode != 0:
        return False, [version, facts, f"exit {init.returncode}, {errors} errors", "skipped", "", ""]
    launch = _launch_commands(cfg, version, database)
    shell = _shell_answers(launch["shell"])
    tests = _tests_pass(launch["test module"])
    login = _serves_login(cfg, version, database, launch["upgrade modules"])
    ok = errors == 0 and (shell, tests, login) == ("ORM ok", "tests ok", "login form")
    return ok, [version, facts, f"exit 0, {errors} errors", shell, tests, login]


def _clean(cfg: WorkspaceConfig, new_clones: list[Path]) -> None:
    for version in cfg.versions:
        database = _database(version)
        subprocess.run(
            ["dropdb", "-h", cfg.db_host, "-p", str(cfg.db_port), "-U", cfg.db_user,
             "--if-exists", database],
            check=False,
        )
        shutil.rmtree(FILESTORE / database, ignore_errors=True)
    shutil.rmtree(cfg.root, ignore_errors=True)
    for clone in new_clones:
        shutil.rmtree(clone, ignore_errors=True)
    print(f"Removed {cfg.root}, its databases and filestores, and {len(new_clones)} new clone(s).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("versions", nargs="*", help="e.g. 12.0 15.0 (default: all)")
    parser.add_argument("--keep", action="store_true", help="leave everything for inspection")
    parser.add_argument("--yes", action="store_true", help="apply without asking")
    args = parser.parse_args()

    versions = args.versions or [f"{major}.0" for major in sorted(ODOO_SUPPORT)]
    cfg = WorkspaceConfig(name=NAME, versions=versions)
    cfg.normalize_defaults()
    cfg.validate()
    refusal = _refuse_if_present(cfg)
    if refusal:
        print(f"Refusing: {refusal}")
        return 1

    host = system.detect_python_version()
    interpreters = {v: resolve_interpreter(v, host_python=host) for v in cfg.versions}
    for version, choice in interpreters.items():
        print(f"Odoo {version}: Python {choice.describe()}")
    new_clones = [cfg.odoo_clone_dir(v) for v in cfg.versions if not cfg.odoo_clone_dir(v).exists()]
    commands = planners.plan_generate_workspace(
        cfg, exists=lambda path: Path(path).exists(), interpreters=interpreters
    )
    system.preview_commands(commands)
    if not args.yes and input("Apply this plan? Type 'yes': ").strip() != "yes":
        print("Nothing applied.")
        return 1

    try:
        system.apply_commands(commands, stop_on_error=False)
        results = [_check(cfg, version) for version in cfg.versions]
    finally:
        if not args.keep:
            _clean(cfg, new_clones)

    print()
    print(render_table(["Odoo", "Python / setuptools", "install", "shell", "test module",
                        "upgrade + /web/login"],
                       [row for _ok, row in results]))
    failed = [row[0] for ok, row in results if not ok]
    print(f"\n{'FAIL: ' + ', '.join(failed) if failed else 'All versions pass.'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
