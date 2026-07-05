"""Execution primitives and host probes (mirrors ``odoo_instance_manager``).

The ``plan → preview → apply`` contract lives here: pure ``planners`` build
``Command`` lists, and *only* ``apply_commands`` runs them, after
``preview_commands`` has shown the plan. Commands run through ``bash -lc`` because
the tool targets a Linux host; on a non-Linux dev box these are exercised by
tests that do not shell out. Standard-library only.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass

from .i18n import t, tf
from .ui import level_text, style, title, wrap_plain_block


@dataclass
class Command:
    description: str
    command: str


def run(command: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["bash", "-lc", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {command}\n"
            f"exit={result.returncode}\n"
            f"stdout={result.stdout}\n"
            f"stderr={result.stderr}"
        )
    return result


def run_streaming(command: str) -> subprocess.CompletedProcess[str]:
    """Run a command, forwarding its output live while also capturing it.

    stdlib-only (``subprocess.Popen``): stderr is merged into stdout so combined
    output appears in real time — useful for long steps (git clone, pip install)
    that would otherwise sit silent. stdin is closed so a command never blocks
    waiting for input. Returns a ``CompletedProcess`` with the accumulated output.
    """
    process = subprocess.Popen(
        ["bash", "-lc", command],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    captured: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
        captured.append(line)
    process.stdout.close()
    returncode = process.wait()
    return subprocess.CompletedProcess(process.args, returncode, "".join(captured), "")


def command_ok(command: str) -> bool:
    return run(command, check=False).returncode == 0


def has_tool(name: str) -> bool:
    """True when an executable ``name`` is on PATH (uses ``command -v``)."""
    return command_ok(f"command -v {name} >/dev/null 2>&1")


def path_exists(path: str) -> bool:
    return command_ok(f"test -e '{path}'")


def preview_commands(commands: list[Command]) -> None:
    """Render the plan as a readable, terminal-width-wrapped list."""
    print(f"\n{title('Execution plan')}")
    indent = "     "
    body_width = max(20, shutil.get_terminal_size((100, 24)).columns - len(indent))
    for index, item in enumerate(commands, start=1):
        print(f"\n{style(f'[{index:02d}]', 'blue', 'bold')} {t(item.description)}")
        for chunk in wrap_plain_block(item.command, body_width):
            print(style(f"{indent}{chunk}", "dim"))


def apply_commands(commands: list[Command], stop_on_error: bool = True) -> None:
    for index, item in enumerate(commands, start=1):
        print(f"\n{style(f'[{index}/{len(commands)}]', 'blue', 'bold')} {t(item.description)}")
        # Stream output live so long steps (git clone/pip install) aren't silent.
        result = run_streaming(item.command)
        if result.returncode != 0:
            print(level_text("ERROR", tf("Command finished with code {}.", result.returncode)))
            if stop_on_error:
                raise RuntimeError(f"Failed running: {item.command}")


def list_dirs(base_path: str) -> list[str]:
    if not os.path.isdir(base_path):
        return []
    return sorted(
        entry
        for entry in os.listdir(base_path)
        if os.path.isdir(os.path.join(base_path, entry)) and not entry.startswith(".")
    )


# --- host probes -----------------------------------------------------------


def detect_os_release() -> dict[str, str]:
    """Parse ``/etc/os-release`` into a dict (e.g. ``ID``, ``VERSION_CODENAME``)."""
    values: dict[str, str] = {}
    try:
        with open("/etc/os-release", encoding="utf-8") as file_handle:
            for raw_line in file_handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        return values
    return values


def detect_postgres_version() -> int | None:
    """Local PostgreSQL server major version via ``SHOW server_version``, or None."""
    result = run(
        'sudo -u postgres psql -tAc "SHOW server_version" 2>/dev/null',
        check=False,
    )
    match = re.search(r"(\d+)", result.stdout.strip())
    if result.returncode == 0 and match:
        return int(match.group(1))
    return None


def detect_tool_version(name: str, args: str = "--version") -> str | None:
    """First line of ``<name> <args>`` output, or None when the tool is absent."""
    if not has_tool(name):
        return None
    result = run(f"{name} {args} 2>&1", check=False)
    text = (result.stdout or result.stderr).strip().splitlines()
    return text[0].strip() if text else None


# --- provisioning probes ---------------------------------------------------


def apt_family() -> str:
    """Return ``"debian"`` when the host is in the Debian/Ubuntu (apt) family, else
    ``""`` (unsupported by this version). Uses ``ID``/``ID_LIKE`` from os-release."""
    release = detect_os_release()
    ident = release.get("ID", "").lower()
    id_like = release.get("ID_LIKE", "").lower()
    if ident in {"debian", "ubuntu"} or "debian" in id_like or "ubuntu" in id_like:
        return "debian"
    return ""


def package_installed(name: str) -> bool:
    """True when a dpkg package is installed (``dpkg -s`` reports installed)."""
    return command_ok(f"dpkg -s {name} 2>/dev/null | grep -q '^Status: install ok installed'")


def wkhtmltopdf_version() -> str | None:
    """Installed wkhtmltopdf version banner (e.g. ``0.12.6 (with patched qt)``), or
    None when absent. Callers inspect the string for ``with patched qt``."""
    if not has_tool("wkhtmltopdf"):
        return None
    result = run("wkhtmltopdf --version 2>/dev/null", check=False)
    text = (result.stdout or result.stderr).strip()
    return text or None


def postgres_installed() -> bool:
    return has_tool("psql") or package_installed("postgresql")


def postgres_running() -> bool:
    """True when the local PostgreSQL server accepts a superuser connection."""
    return command_ok("sudo -u postgres psql -tAc 'SELECT 1' >/dev/null 2>&1")


def db_role_exists(role: str) -> bool:
    query = f"sudo -u postgres psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='{role}'\""
    result = run(query, check=False)
    return result.returncode == 0 and "1" in result.stdout
