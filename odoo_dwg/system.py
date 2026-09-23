"""Execution primitives and host probes (mirrors ``odoo_instance_manager``).

The ``plan → preview → apply`` contract lives here: pure ``planners`` build
``Command`` lists, and *only* ``apply_commands`` runs them, after
``preview_commands`` has shown the plan. Commands run through ``bash -lc`` because
the tool targets a Linux host; on a non-Linux dev box these are exercised by
tests that do not shell out. Standard-library only.
"""

from __future__ import annotations

import contextlib
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

from . import pghba
from .i18n import t, tf
from .models import DB_ROLE_RE, DEFAULT_DB_ROLE, Command  # noqa: F401 (re-exported)
from .ui import level_tag, level_text, style, title, wrap_plain_block

#: Linux refuses a single argument longer than 128 KiB (``MAX_ARG_STRLEN``), and a
#: command writing a generated file carries the file in a heredoc: a findings
#: ledger or a table of twenty thousand rows failed with "Argument list too long"
#: before bash started. Past this size the command is run from a script file.
_ARG_LIMIT = 100_000


class _Bash:
    """``bash -lc <command>``, or ``bash -l <script>`` for a command too long to be
    an argument; the script (mode 600) is removed afterwards."""

    def __init__(self, command: str):
        self.script: str | None = None
        if len(command.encode("utf-8")) <= _ARG_LIMIT:
            self.argv = ["bash", "-lc", command]
            return
        import tempfile
        handle, self.script = tempfile.mkstemp(prefix="odwg-step-", suffix=".sh")
        with os.fdopen(handle, "w", encoding="utf-8") as script:
            script.write(command)
        self.argv = ["bash", "-l", self.script]

    def __enter__(self) -> list[str]:
        return self.argv

    def __exit__(self, *_exc: object) -> None:
        if self.script:
            with contextlib.suppress(OSError):
                os.unlink(self.script)


def run(command: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    with _Bash(command) as argv:
        result = subprocess.run(
            argv,
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
    with _Bash(command) as argv:
        process = subprocess.Popen(
            argv,
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
    kept = (output.strip() or t("(no output)")).splitlines()
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
        f'sudo -n -u postgres psql -X -p {int(port)} -tAc "SHOW server_version" 2>/dev/null',
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


def url_status(url: str, timeout: float = 20.0) -> tuple[int | None, str]:
    """The HTTP status a URL finally answers with (redirects followed), or the error.

    ``HEAD`` first, since only the answer matters; ``GET`` when a server refuses
    ``HEAD`` with 405. Some hosts (GitHub among them) reject a request without a
    User-Agent, so one is sent."""
    import urllib.error
    import urllib.request

    for method in ("HEAD", "GET"):
        request = urllib.request.Request(url, method=method,
                                         headers={"User-Agent": "odoo-dwg link check"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, ""
        except urllib.error.HTTPError as error:
            if error.code == 405 and method == "HEAD":
                continue
            return error.code, str(error.reason)
        except (urllib.error.URLError, OSError, ValueError) as error:
            return None, str(getattr(error, "reason", error))
    return None, "no answer"


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
        f"psql -X -h 127.0.0.1 -p {int(port)} -U {shlex.quote(role)} -d postgres "
        "-w -tAc 'SELECT 1' >/dev/null 2>&1"
    )
    if command_ok(login):
        return True
    query = shlex.quote(f"SELECT 1 FROM pg_roles WHERE rolname='{role}'")
    result = run(f"sudo -n -u postgres psql -X -p {int(port)} -tAc {query} 2>/dev/null", check=False)
    if result.returncode != 0:
        return None
    return "1" in result.stdout


_PG_HBA_COLUMNS = (
    "SELECT type, array_to_string(database, ','), array_to_string(user_name, ','), "
    "coalesce(address, ''), coalesce(netmask, ''), auth_method, "
)
PG_HBA_RULES_QUERY = (
    _PG_HBA_COLUMNS + "coalesce(file_name, ''), coalesce(line_number::text, '0'), "
    "coalesce(error, '') FROM pg_hba_file_rules ORDER BY rule_number"
)
# `file_name` and `rule_number` exist from PostgreSQL 15; the view itself from 10,
# and `include` directives (the only way a rule comes from another file) from 16.
# So below 15 the configured file is the only one there is, and `hba_file` names it.
PG_HBA_RULES_QUERY_PRE15 = (
    _PG_HBA_COLUMNS + "(SELECT setting FROM pg_settings WHERE name = 'hba_file'), "
    "coalesce(line_number::text, '0'), coalesce(error, '') "
    "FROM pg_hba_file_rules ORDER BY line_number"
)


def pg_hba_rules(port: int = 5432) -> list[pghba.Rule] | None:
    """The server's own view of its `pg_hba.conf`, or None when it cannot be had.

    `pg_hba_file_rules` (PostgreSQL 10+) is the parsed rule set: continuations
    folded, `include*` expanded and attributed to the file each rule came from,
    list fields split. It is read at query time, so it also answers "what does the
    file say now" before a reload. Superuser-only, hence `sudo -n`, which fails
    rather than prompting.
    """
    for query in (PG_HBA_RULES_QUERY, PG_HBA_RULES_QUERY_PRE15):
        result = run(
            # $'\t' and not '\t': the second gives psql a literal backslash-t.
            f"sudo -n -u postgres psql -X -p {int(port)} -w -tAF$'\\t' "
            f"-c {shlex.quote(query)} 2>/dev/null",
            check=False,
        )
        if result.returncode == 0:
            return pghba.parse_rules(result.stdout)
    return None


def pg_hba_loopback_state(role: str, port: int = 5432) -> tuple[bool, bool] | None:
    """``(blanket_trust, role_trusted)`` for TCP connections, from the server.

    ``blanket_trust``: a TCP rule trusting *every* role, whatever address it
    names — any local user may then connect as any role, ``postgres`` included.

    ``role_trusted``: the development role's trust rule is the one a connection
    **reaches**. `pg_hba` is first-match-wins, so a rule below one that already
    matches is never read, and reporting it as trusted would claim a narrowing
    that does not work.

    None when the answer cannot be had: PostgreSQL is not running, the view is not
    readable without a password, or the server reports a rule it could not parse.
    A caller must not mistake "unknown" for "already narrow".
    """
    if not DB_ROLE_RE.fullmatch(role):
        return None
    rules = pg_hba_rules(port)
    if rules is None or not rules or pghba.unreadable(rules) is not None:
        return None
    if pghba.names_roles_by_pattern(rules) is not None:
        # A trust rule for `/regex` or `+group` roles: whether it covers every
        # role cannot be told from here, so this is unknown, not "fine".
        return None
    # The view cannot tell the keyword `all` from a role *named* `all`, and it
    # reports a comma list as separate elements either way. Correct every rule
    # from its own line once, and both questions below are asked of the same,
    # corrected reading — they used to disagree, and `provision check` then
    # reported a working trust as missing on every run.
    corrected = _as_the_server_reads_them(rules)
    return (
        pghba.blanket_trust(corrected) is not None,
        pghba.role_is_reached(corrected, role),
    )


def _as_the_server_reads_them(rules: list[pghba.Rule]) -> list[pghba.Rule]:
    """Rules whose `all` is marked as quoted when their own line shows it so.

    The line is consulted for exactly one bit the view lost — whether `all` was
    written ``"all"`` — and is allowed to say nothing else. Its reading is used
    only when, with that mark removed, it names the same roles the server
    reported; any other difference means the line was tokenized differently
    from `hba.c` (a list continued after a blank, a `#` inside quotes, an
    `@file`, a non-ASCII blank …), and then the server's answer stands. Four
    rounds of fixes each let the line *narrow* the server's answer in one more
    shape, and each one was a host reported as narrowed while every role could
    connect; a line that can only confirm cannot do that.

    A line that cannot be read keeps the view's answer for the same reason.
    """
    lines: dict[str, list[str]] = {}
    out: list[pghba.Rule] = []
    for rule in rules:
        if "all" not in rule.users or not rule.file:
            out.append(rule)
            continue
        if rule.file not in lines:
            text = read_text(rule.file)
            # Split on "\n" only: the server counts lines that way, and
            # ``splitlines`` also breaks on form feeds and U+2028, which would
            # point this at a neighbouring rule.
            lines[rule.file] = text.split("\n") if text else []
        file_lines = lines[rule.file]
        if not 1 <= rule.line <= len(file_lines):
            out.append(rule)
            continue
        elements = pghba.role_elements(file_lines[rule.line - 1])
        if elements is None:
            out.append(rule)
            continue
        unmarked = sorted("all" if element == '"all"' else element for element in elements)
        if unmarked != sorted(rule.users):
            out.append(rule)
            continue
        out.append(replace(rule, users=elements))
    return out


def journal_since(tag: str, since: str, until: str = "") -> str:
    """The system journal for one unit tag between two instants, or "".

    The driver writes each step's start and end in the form the journal's own
    time filters take, so a step's window is asked for rather than estimated.
    Reading the journal needs no root for a user in the `adm` or
    `systemd-journal` group; where it does, this returns nothing rather than
    prompting, and the report says the firewall's answers were not available.
    """
    if not since:
        return ""
    command = (
        f"journalctl -t {shlex.quote(tag)} --no-pager "
        f"--since {shlex.quote(since)}"
    )
    if until:
        command += f" --until {shlex.quote(until)}"
    result = run(command, check=False)
    return result.stdout if result.returncode == 0 else ""


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


def read_dir_files(path: str, suffix: str = "") -> dict[str, str] | None:
    """Every readable file of a directory as ``name -> content``, or None when the
    directory itself cannot be listed.

    None and {} are different answers: a rules directory that is not there is not
    a rules directory that is empty, and reporting the first as the second would
    say every rule is missing.
    """
    try:
        entries = sorted(Path(path).iterdir())
    except OSError:
        return None
    found: dict[str, str] = {}
    for entry in entries:
        if suffix and not entry.name.endswith(suffix):
            continue
        try:
            found[entry.name] = entry.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return found


def psql_rows(
    query: str, db: str, host: str = "127.0.0.1", port: int = 5432, user: str = DEFAULT_DB_ROLE
) -> list[list[str]] | None:
    """Tab-separated rows from a read-only query, or None on any failure.

    ``-tAF$'\t'``: unaligned, no header, tab-separated — the same reading
    ``pg_hba_rules`` uses. A backslash-t in single quotes would reach psql as two
    characters, not a tab."""
    command = (
        f"psql -X -w -h {shlex.quote(host)} -p {int(port)} -U {shlex.quote(user)} "
        f"-d {shlex.quote(db)} -tAF$'\\t' -c {shlex.quote(query)} 2>/dev/null"
    )
    result = run(command, check=False)
    if result.returncode != 0:
        return None
    return [line.split("\t") for line in result.stdout.splitlines() if line.strip()]


def psql_scalar(
    query: str, db: str, host: str = "127.0.0.1", port: int = 5432, user: str = DEFAULT_DB_ROLE
) -> str | None:
    """Single-value ``psql`` query against an existing database, or None on any
    failure. Queries are caller-built from validated identifiers; the operator-
    shaped values (db/host/user and the query itself) are shell-quoted here."""
    command = (
        # -w: fail instead of prompting when the host is not on trust auth.
        f"psql -X -w -h {shlex.quote(host)} -p {int(port)} -U {shlex.quote(user)} "
        f"-d {shlex.quote(db)} -tAc {shlex.quote(query)} 2>/dev/null"
    )
    result = run(command, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


# --- taking in a client copy (reads only) -----------------------------------------------

def git_output(repo: Path | str, *args: str) -> str | None:
    """A git command's standard output in ``repo``, or None when it fails. Reads only:
    the callers ask for logs, trees and remotes, never for anything that writes."""
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def git_raw_log(repo: Path | str, paths: list[str], batch: int = 400) -> str | None:
    """``git log --raw`` for these paths, merges included, in batches so that a core
    with thousands of differing files does not exceed the argument limit."""
    out = []
    for start in range(0, len(paths), batch):
        text = git_output(repo, "log", "--raw", "--no-abbrev", "--no-renames",
                          "--diff-merges=separate", "--format=@%H %cs", "HEAD", "--",
                          *paths[start:start + batch])
        if text is None:
            return None
        out.append(text)
    return "".join(out)


def scan_manifests(root: Path | str, dirs: list[str]) -> list[tuple[str, str, str]]:
    """``(directory, module, manifest)`` for every module directly under each of
    ``dirs`` (relative to ``root``), in the given order. Both manifest names count:
    Odoo up to 12.0 still loads the legacy ``__openerp__.py``."""
    from .intake import MANIFESTS

    found: list[tuple[str, str, str]] = []
    for directory in dirs:
        base = Path(root) / directory
        if not base.is_dir():
            continue
        for module in sorted(p for p in base.iterdir() if p.is_dir()):
            manifest = next((m for m in MANIFESTS if (module / m).is_file()), None)
            if manifest:
                found.append((directory, module.name, manifest))
    return found


def tree_blobs(root: Path | str, subdirs: tuple[str, ...] = ("addons", "odoo/addons")
               ) -> dict[str, str]:
    """``{path: git blob id}`` of every file under ``subdirs`` of ``root``, paths
    relative to ``root`` — the shape ``git ls-tree -r`` gives for a commit."""
    from .intake import git_blob_id

    base = Path(root)
    blobs: dict[str, str] = {}
    for sub in subdirs:
        top = base / sub
        if not top.is_dir():
            continue
        for path in top.rglob("*"):
            if path.is_file() and not path.is_symlink():
                blobs[str(path.relative_to(base))] = git_blob_id(path.read_bytes())
    return blobs


def repo_state(path: Path | str) -> dict[str, str]:
    """A client repository as delivered: remote, branch, commit, commits ahead of and
    behind its upstream, and files changed but not committed. Empty when not git.

    Local only: the client's remotes may be private, and nothing here contacts
    them — "ahead" and "behind" are against the upstream as the client last
    fetched it. The remote URL is recorded without any credentials in it."""
    from .intake import redact_url

    if not (Path(path) / ".git").exists():
        return {}
    def one(*args: str) -> str:
        return (git_output(path, *args) or "").strip()
    upstream = one("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    counts = one("rev-list", "--left-right", "--count", f"{upstream}...HEAD") if upstream else ""
    behind, ahead = (counts.split() + ["", ""])[:2] if counts else ("", "")
    dirty = git_output(path, "--no-optional-locks", "status", "--porcelain") or ""
    return {
        "remote": redact_url(one("config", "--get", "remote.origin.url")),
        "branch": one("rev-parse", "--abbrev-ref", "HEAD"),
        "head": one("rev-parse", "HEAD"),
        "last_commit": one("log", "-1", "--format=%cs"),
        "upstream": upstream, "ahead": ahead, "behind": behind,
        "dirty": ";".join(line[3:] for line in dirty.splitlines() if line.strip()),
    }


def archive_top(archive: Path | str) -> str | None:
    """The first path component of a tar archive's first member, or None.

    Stops at the first line: listing a filestore archive of many gigabytes whole
    to learn its top directory took minutes."""
    try:
        proc = subprocess.Popen(["tar", "-tf", str(archive)], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True)
    except OSError:
        return None
    first = ""
    assert proc.stdout is not None
    for line in proc.stdout:
        if line.strip():
            first = line.strip()
            break
    proc.kill()
    proc.wait()
    return first.removeprefix("./").split("/")[0] or None
