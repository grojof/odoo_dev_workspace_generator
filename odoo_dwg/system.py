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
import shlex
import shutil
import subprocess

from .i18n import t, tf
from .models import DB_ROLE_RE, DEFAULT_DB_ROLE, Command  # noqa: F401 (re-exported)
from .ui import level_tag, level_text, style, title, wrap_plain_block


def run(command: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["bash", "-lc", command],
        # A step that reads stdin would swallow the operator's keystrokes while
        # its prompt sits invisible in the captured output (quiet is the
        # default). Commands are non-interactive by construction.
        stdin=subprocess.DEVNULL,
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
    return command_ok(f"command -v {shlex.quote(name)} >/dev/null 2>&1")




def preview_commands(commands: list[Command]) -> None:
    """Render the plan as a readable, terminal-width-wrapped list."""
    print(f"\n{title('Execution plan')}")
    indent = "     "
    body_width = max(20, shutil.get_terminal_size((100, 24)).columns - len(indent))
    for index, item in enumerate(commands, start=1):
        print(f"\n{style(f'[{index:02d}]', 'blue', 'bold')} {t(item.description)}")
        for chunk in wrap_plain_block(item.command, body_width):
            print(style(f"{indent}{chunk}", "dim"))


# Lines worth showing even when a step succeeds.
_NOTEWORTHY = re.compile(r"\b(warn|warning|deprecat|error|fail|failed)\b", re.IGNORECASE)
_MAX_NOTEWORTHY = 10
_verbose = False


def set_verbose(verbose: bool) -> None:
    """Whether applying a plan streams every line (``--verbose``) or prints one
    line per step, keeping only warnings and the output of a step that fails."""
    global _verbose
    _verbose = verbose



def _tail(output: str, lines: int = 40) -> str:
    """The end of a failed step's output, indented — where the reason usually is."""
    kept = (output.strip() or "(no output)").splitlines()
    shown = kept[-lines:]
    prefix = "" if len(kept) <= lines else f"    … {len(kept) - lines} earlier line(s)\n"
    return prefix + "\n".join(f"    {line}" for line in shown)


def _noteworthy(output: str) -> list[str]:
    lines = [line.rstrip() for line in output.splitlines() if _NOTEWORTHY.search(line)]
    return lines[:_MAX_NOTEWORTHY]


def apply_commands(commands: list[Command], stop_on_error: bool = True) -> None:
    """Run a previewed plan, reporting per step.

    Quiet (the default): one line per step, plus any warning a step printed. A
    step that fails prints everything it produced, so nothing needed to diagnose
    it is lost. Verbose: every line, live, which is what long steps (git clone,
    pip install) look like while they work."""
    total = len(commands)
    for index, item in enumerate(commands, start=1):
        label = f"{style(f'[{index}/{total}]', 'blue', 'bold')} {t(item.description)}"
        if _verbose:
            print(f"\n{label}")
            result = run_streaming(item.command)
        else:
            print(f"{label} … ", end="", flush=True)
            result = run(item.command)
            print(level_tag("OK") if result.returncode == 0 else level_tag("ERROR"))
            output = (result.stdout or "") + (result.stderr or "")
            if result.returncode == 0:
                for line in _noteworthy(output):
                    print(f"    {line}")
            else:
                print(_tail(output))
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


def detect_postgres_version(port: int = 5432) -> int | None:
    """Major version of the local server on ``port``, or None. From
    ``pg_lsclusters`` (no authentication), else ``SHOW server_version`` through
    ``sudo -n``, which fails rather than prompting."""
    for major, cluster_port in _online_clusters() or []:
        if cluster_port == port:
            return major
    result = run(
        f'sudo -n -u postgres psql -p {int(port)} -tAc "SHOW server_version" 2>/dev/null',
        check=False,
    )
    match = re.search(r"(\d+)", result.stdout.strip())
    if result.returncode == 0 and match:
        return int(match.group(1))
    return None


def detect_python_version() -> str | None:
    """The host ``python3`` minor version as ``"3.12"``, or None when absent."""
    result = run("python3 -c 'import sys; print(\"%d.%d\" % sys.version_info[:2])'", check=False)
    text = result.stdout.strip()
    return text if re.fullmatch(r"\d+\.\d+", text) else None


def uv_python_minors() -> list[str]:
    """Minor versions ``uv`` can provide (installed or downloadable), ascending.

    Empty when ``uv`` is absent, which is how callers tell "no uv" from "uv has
    nothing suitable"."""
    if not has_tool("uv"):
        return []
    result = run("uv python list 2>/dev/null", check=False)
    if result.returncode != 0:
        return []
    minors = {
        f"{match.group(1)}.{match.group(2)}"
        for match in re.finditer(r"^cpython-(\d+)\.(\d+)", result.stdout, re.MULTILINE)
    }
    return sorted(minors, key=lambda text: tuple(int(part) for part in text.split(".")))




# --- provisioning probes ---------------------------------------------------


def package_installed(name: str) -> bool:
    """True when a dpkg package is installed (``dpkg -s`` reports installed)."""
    return command_ok(
        f"dpkg -s {shlex.quote(name)} 2>/dev/null | grep -q '^Status: install ok installed'"
    )


def wkhtmltopdf_version() -> str | None:
    """Installed wkhtmltopdf version banner (e.g. ``0.12.6 (with patched qt)``), or
    None when absent. Callers inspect the string for ``with patched qt``."""
    if not has_tool("wkhtmltopdf"):
        return None
    result = run("wkhtmltopdf --version 2>/dev/null", check=False)
    text = (result.stdout or result.stderr).strip()
    return text or None


def deb_version(package: str) -> str | None:
    """Installed Debian package version (e.g. ``1.8.0-1``), or None when absent."""
    result = run(
        f"dpkg-query -W -f='${{Status}} ${{Version}}' {shlex.quote(package)} 2>/dev/null",
        check=False,
    )
    parts = result.stdout.split()
    return parts[-1] if result.returncode == 0 and "installed" in parts else None


def service_active(unit: str) -> bool:
    return command_ok(f"systemctl is-active --quiet {shlex.quote(unit)}")


def read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def mailpit_version(binary: str) -> str | None:
    """``1.31.2`` from ``mailpit version``, or None when the binary is absent."""
    if not os.path.exists(binary):
        return None
    match = re.search(r"v(\d+\.\d+\.\d+)", run(f"{shlex.quote(binary)} version", check=False).stdout)
    return match.group(1) if match else None


def apt_purge_removals(packages: tuple[str, ...] | list[str]) -> list[str]:
    """What ``apt-get purge --autoremove <packages>`` would remove, simulated
    (``-s``: read-only, no root needed)."""
    names = " ".join(shlex.quote(p) for p in packages)
    simulated = run(f"apt-get -s purge --autoremove {names}", check=False).stdout
    return sorted({line.split()[1] for line in simulated.splitlines() if line.startswith("Purg ")})


def postgres_installed() -> bool:
    return has_tool("psql") or package_installed("postgresql")


def _online_clusters() -> list[tuple[int, int]] | None:
    """``[(major, port), …]`` of online clusters from ``pg_lsclusters``, which
    reads the cluster layout without authenticating; None when it is absent."""
    if not has_tool("pg_lsclusters"):
        return None
    result = run("pg_lsclusters --no-header", check=False)
    clusters = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[3].startswith("online") and parts[0].isdigit() \
                and parts[2].isdigit():
            clusters.append((int(parts[0]), int(parts[2])))
    return clusters


def postgres_running(port: int = 5432) -> bool:
    """True when a local server is up on ``port``. Never authenticates and never
    prompts: ``pg_lsclusters``, else ``pg_isready`` on loopback."""
    clusters = _online_clusters()
    if clusters is not None:
        return any(cluster_port == port for _major, cluster_port in clusters)
    return command_ok(f"pg_isready -q -h 127.0.0.1 -p {int(port)}")


def db_role_exists(role: str, port: int = 5432) -> bool | None:
    """Whether a PostgreSQL role exists; None when that cannot be told without a
    password prompt. Tries the role itself over loopback (the development trust
    rule), then ``sudo -n`` as postgres, which fails instead of prompting."""
    if not DB_ROLE_RE.fullmatch(role):
        return False
    login = (
        f"psql -h 127.0.0.1 -p {int(port)} -U {shlex.quote(role)} -d postgres "
        "-w -tAc 'SELECT 1' >/dev/null 2>&1"
    )
    if command_ok(login):
        return True
    query = shlex.quote(f"SELECT 1 FROM pg_roles WHERE rolname='{role}'")
    result = run(f"sudo -n -u postgres psql -p {int(port)} -tAc {query} 2>/dev/null", check=False)
    if result.returncode != 0:
        return None
    return "1" in result.stdout


def pg_hba_loopback_state(role: str, port: int = 5432) -> tuple[bool, bool] | None:
    """``(blanket_trust, role_trusted)`` for loopback in the server's ``pg_hba.conf``.

    ``blanket_trust`` is a ``host all all 127.0.0.1/32|::1/128 trust`` line — any
    local user may then connect as any role, ``postgres`` included. ``role_trusted``
    is the development role's own loopback trust line. None when the file cannot
    be located or read (it is root-owned), so a caller cannot mistake "unknown"
    for "already narrow".
    """
    if not DB_ROLE_RE.fullmatch(role):
        return None
    path = run(
        f"sudo -n -u postgres psql -p {int(port)} -tAc 'SHOW hba_file;' 2>/dev/null", check=False
    ).stdout.strip()
    text = read_text(path) if path else None
    if not text:
        return None
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    # pg_hba spells loopback several ways; a blanket trust is a blanket trust
    # however it is written.
    blanket = re.compile(
        r"^host\s+all\s+all\s+(127\.0\.0\.1/32|::1/128|localhost|samehost|samenet)\s+trust\b"
    )
    own = re.compile(rf"^host\s+all\s+{re.escape(role)}\s+127\.0\.0\.1/32\s+trust\b")
    return (
        any(blanket.match(line) for line in lines),
        any(own.match(line) for line in lines),
    )


# --- migration preflight probes --------------------------------------------


def pg_restore_lists(dump_path: str) -> tuple[bool, str]:
    """(ok, detail): whether ``pg_restore --list`` parses the dump — which also
    proves the custom/tar format the driver needs (a plain-SQL dump fails here)."""
    result = run(f"pg_restore --list {shlex.quote(dump_path)} >/dev/null", check=False)
    if result.returncode == 0:
        return True, ""
    text = (result.stderr or result.stdout).strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return False, lines[-1] if lines else "pg_restore --list failed"


def psql_scalar(
    query: str, db: str, host: str = "127.0.0.1", port: int = 5432, user: str = DEFAULT_DB_ROLE
) -> str | None:
    """Single-value ``psql`` query against an existing database, or None on any
    failure. Queries are caller-built from validated identifiers; the operator-
    shaped values (db/host/user and the query itself) are shell-quoted here."""
    command = (
        # -w: fail instead of prompting when the host is not on trust auth.
        f"psql -w -h {shlex.quote(host)} -p {int(port)} -U {shlex.quote(user)} "
        f"-d {shlex.quote(db)} -tAc {shlex.quote(query)} 2>/dev/null"
    )
    result = run(command, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()
