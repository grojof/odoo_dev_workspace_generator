#!/usr/bin/env python3
"""Execute the generated `pg_hba.conf` rewriter against real files — and ask
PostgreSQL whether the result means what the tool says it means.

`plan_pg_hba_trust` rewrites a root-owned authentication file with `sed`, and the
unit suite may not shell out (CLAUDE.md), so its assertions are on the plan's
*text*. Four audit rounds found the same class of bug behind that: a blanket
trust written `localhost`, then indented or `hostnossl`, then on an address that
merely contains loopback, then on `hostssl` — each surviving the narrowing while
the check reported `trust for odoo only`.

This tool renders the real command, points only its `SHOW hba_file;` lookup at a
fixture, runs it over every shape of that file, and asserts the result. It does
so twice over:

- against a **field-based reading** of the file, written independently of the
  code it checks (the earlier version of this tool asserted with a copy of
  `system.py`'s own regex, which is how `hostssl` passed three rounds of it);
- against **PostgreSQL itself**, in a throwaway cluster this creates and destroys
  — `pg_hba_file_rules` is the server's own parse of the file, and a connection
  through it is the only proof that a narrowing narrowed anything.

    python tools/verify_pg_hba_trust.py

Needs `bash` and `sed`; uses the host's PostgreSQL *binaries* when they are
present and says so when they are not. No network, no root, the host's own
cluster untouched, nothing written outside a temp directory.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odoo_dwg import pghba, planners, system  # noqa: E402

ROLE = "odoo"
LOOKUP = 'PGHBA=$(sudo -u postgres psql -X -tAc "SHOW hba_file;")'

UBUNTU_DEFAULT = """\
local   all             postgres                                peer
local   all             all                                     peer
host    all             all             127.0.0.1/32            scram-sha-256
host    all             all             ::1/128                 scram-sha-256
"""

BLANKET_CIDR = """\
local   all             postgres                                peer
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
"""

BLANKET_NAMED = """\
local   all             postgres                                peer
host    all             all             localhost               trust
host    all             all             samehost                trust
"""

NO_HOST_RULES = "local   all             postgres                                peer\n"

ALREADY_NARROW = """\
local   all             postgres                                peer
host    all             odoo             127.0.0.1/32            trust
host    all             odoo             ::1/128                 trust
host    all             all             127.0.0.1/32            scram-sha-256
"""

# pg_hba skips leading blanks, accepts hostnossl, and takes `address netmask`
# as well as CIDR. Each of these is a live blanket trust.
INDENTED = """\
local   all             postgres                                peer
  host    all             all             127.0.0.1/32            trust
"""

LEGACY_NETMASK = """\
local   all             postgres                                peer
host all all 127.0.0.1 255.255.255.255 trust
"""

HOSTNOSSL = """\
local   all             postgres                                peer
hostnossl all all 127.0.0.1/32 trust
"""

# Addresses that contain loopback without naming it. `all` is what the official
# postgres image writes for POSTGRES_HOST_AUTH_METHOD=trust.
ANY_ADDRESS = """\
local   all             postgres                                peer
host all all all trust
"""

WORLD = """\
local   all             postgres                                peer
host all all 0.0.0.0/0 trust
host all all ::0/0 trust
"""

LOOPBACK_RANGE = """\
local   all             postgres                                peer
host all all 127.0.0.0/8 trust
"""

# The connection type the supported host actually uses: Ubuntu 24.04 ships
# ssl = on, and libpq defaults to sslmode=prefer, so a hostssl record is the one
# consulted for a loopback connection.
HOSTSSL = """\
local   all             postgres                                peer
hostssl all             all             127.0.0.1/32            trust
host    all             all             127.0.0.1/32            scram-sha-256
"""

HOSTGSSENC = """\
local   all             postgres                                peer
hostgssenc all all 127.0.0.1/32 trust
"""

# No trailing newline: appending must not fuse onto the last record.
NO_FINAL_NEWLINE = "local   all             postgres                                peer"

# The role's line is there, but a rule for every role above it decides the
# connection first, so it is never read.
SHADOWED_ROLE = """\
local   all             postgres                                peer
host    all             all             127.0.0.1/32            scram-sha-256
host    all             odoo            127.0.0.1/32            trust
"""

# The role already has a trust rule, but on a connection type that is never
# consulted with TLS on. Counting it as the role's line would insert nothing and
# then fail a verification the operator cannot get past by re-running.
ROLE_ON_HOSTSSL = """\
local   all             postgres                                peer
hostssl all             odoo            127.0.0.1/32            trust
host    all             all             127.0.0.1/32            scram-sha-256
"""

# A rule this tool must not touch: the method is not trust, and "trust" only
# appears in a comment.
NOT_A_TRUST = """\
local   all             postgres                                peer
host    all             all             127.0.0.1/32            scram-sha-256 # was trust
"""

CASES = [
    ("the Ubuntu default", UBUNTU_DEFAULT),
    ("a blanket loopback trust (CIDR)", BLANKET_CIDR),
    ("a blanket loopback trust (localhost/samehost)", BLANKET_NAMED),
    ("a file with no host rules at all", NO_HOST_RULES),
    ("a file this tool already narrowed", ALREADY_NARROW),
    ("an indented blanket trust", INDENTED),
    ("a blanket trust in address/netmask form", LEGACY_NETMASK),
    ("a hostnossl blanket trust", HOSTNOSSL),
    ("a blanket trust on every address", ANY_ADDRESS),
    ("a blanket trust open to the network", WORLD),
    ("a blanket trust on the loopback range", LOOPBACK_RANGE),
    ("a password rule whose comment mentions trust", NOT_A_TRUST),
    ("a role line shadowed by an earlier rule", SHADOWED_ROLE),
    ("a hostssl blanket trust", HOSTSSL),
    ("a hostgssenc blanket trust", HOSTGSSENC),
    ("a file with no trailing newline", NO_FINAL_NEWLINE),
    ("the role's own trust rule on hostssl", ROLE_ON_HOSTSSL),
]

# --- an oracle that is not the implementation ------------------------------
#
# This tool used to assert with a copy of `system.py`'s regex, so every shape
# both missed passed as "no blanket trust survives" — which is how a `hostssl`
# trust sailed through three rounds of it. These read records by *field*, the way
# pg_hba's own parser does, so they can disagree with the code they check.

_NETMASK = re.compile(r"^[0-9a-fA-F.:]+$")


def _records(text: str) -> list[tuple[str, str, str, str]]:
    """``(type, database, user, method)`` per rule line, fields split on blanks."""
    out: list[tuple[str, str, str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        kind = fields[0]
        if kind == "local":
            if len(fields) >= 4:
                out.append((kind, fields[1], fields[2], fields[3]))
            continue
        if not kind.startswith("host") or len(fields) < 5:
            continue
        # host<type> DATABASE USER ADDRESS [NETMASK] METHOD
        #            [1]      [2]  [3]     [4]       [4 or 5]
        method_at = 4
        if "/" not in fields[3] and len(fields) > 5 and _NETMASK.match(fields[4]):
            method_at = 5
        if len(fields) > method_at:
            out.append((kind, fields[1], fields[2], fields[method_at]))
    return out


def _has_blanket_trust(text: str) -> bool:
    """Any TCP rule trusting every role, whatever address it names."""
    return any(
        kind.startswith("host") and db == "all" and user == "all" and method == "trust"
        for kind, db, user, method in _records(text)
    )


def _role_is_reached(text: str) -> bool:
    """First match wins: the role's own trust rule, before any rule for every role."""
    for kind, db, user, method in _records(text):
        if kind.startswith("host") and user == ROLE and method == "trust":
            return True
        if kind.startswith("host") and db == "all" and user == "all":
            return False
    return False


class Cluster:
    """A PostgreSQL cluster of our own, in a temp directory.

    It exists so the assertions have an oracle this project did not write: the
    server parses each fixture itself (`pg_hba_file_rules`) and answers a real
    connection. It never touches the host's cluster — its own data directory,
    its own port, its own unix socket, and `initdb` refuses to run as root, so
    this stays a developer-machine tool.
    """

    def __init__(self, root: Path, bindir: Path) -> None:
        self.root = root
        self.data = root / "data"
        self.port = _free_port()
        self.bin = bindir

    def start(self) -> None:
        subprocess.run(
            [str(self.bin / "initdb"), "-D", str(self.data), "-U", "postgres", "--auth=trust",
             "--no-sync"],
            check=True, capture_output=True, text=True,
        )
        # TLS on, like the supported host (Ubuntu ships ssl = on): without it the
        # server rejects every `hostssl` rule as unusable, and those are exactly
        # the rules a loopback connection is matched against there.
        options = f"-p {self.port} -k {self.root} -c listen_addresses=127.0.0.1"
        options += " -c ssl=on" if self._make_certificate() else " -c ssl=off"
        subprocess.run(
            [str(self.bin / "pg_ctl"), "-D", str(self.data), "-w", "-l", str(self.root / "pg.log"),
             "-o", options, "start"],
            check=True, capture_output=True, text=True,
        )
        self.sql(f"CREATE ROLE {ROLE} LOGIN CREATEDB")

    def _make_certificate(self) -> bool:
        """A self-signed certificate for the cluster, if openssl is here."""
        if not shutil.which("openssl"):
            return False
        result = subprocess.run(
            ["openssl", "req", "-new", "-x509", "-days", "1", "-nodes", "-subj", "/CN=localhost",
             "-out", str(self.data / "server.crt"), "-keyout", str(self.data / "server.key")],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return False
        (self.data / "server.key").chmod(0o600)
        return True

    def stop(self) -> None:
        subprocess.run(
            [str(self.bin / "pg_ctl"), "-D", str(self.data), "-m", "immediate", "-w", "stop"],
            check=False, capture_output=True, text=True,
        )

    def sql(self, query: str, user: str = "postgres", host: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.bin / "psql"), "-h", host or str(self.root), "-p", str(self.port),
             "-U", user, "-d", "postgres", "-w", "-tAF\t", "-c", query],
            capture_output=True, text=True,
        )

    def load(self, content: str) -> None:
        """Point the cluster at a fixture and make it re-read it.

        A `local all all trust` line is prepended so this tool can always reach
        its own cluster over the socket — the fixtures' own `local … peer` rules
        would reject it, since the OS user is not `postgres`. Every question asked
        here is about `host` rules, which that line does not affect.
        """
        (self.data / "pg_hba.conf").write_text(
            "local all all trust\n" + content, encoding="utf-8"
        )
        self.sql("SELECT pg_reload_conf()")
        time.sleep(0.2)

    def rules(self) -> list[pghba.Rule]:
        return pghba.parse_rules(self.sql(system.PG_HBA_RULES_QUERY).stdout)

    def role_can_connect_over_tcp(self) -> bool:
        """Without a password: the whole point of the development trust line."""
        env = dict(os.environ, PGPASSWORD="")
        result = subprocess.run(
            [str(self.bin / "psql"), "-h", "127.0.0.1", "-p", str(self.port), "-U", ROLE,
             "-d", "postgres", "-w", "-tAc", "SELECT 1"],
            capture_output=True, text=True, env=env,
        )
        return result.returncode == 0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _postgres_bindir() -> Path | None:
    """Where initdb lives: on PATH, or in the versioned directory Debian uses."""
    found = shutil.which("initdb")
    if found:
        return Path(found).parent
    candidates = sorted(Path("/usr/lib/postgresql").glob("*/bin/initdb"), reverse=True)
    return candidates[0].parent if candidates else None


def _script(into: Path) -> Path:
    command = next(
        c.command for c in planners.plan_pg_hba_trust(ROLE) if "PGHBA=" in c.command
    )
    assert LOOKUP in command, "the psql lookup changed — update this tool"
    path = into / "narrow.sh"
    path.write_text(command.replace(LOOKUP, 'PGHBA="$1"'), encoding="utf-8")
    return path


def main() -> int:
    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        print(f"{'ok  ' if condition else 'FAIL'}  {label}")
        if not condition:
            failures.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory(prefix="odwg-pghba-") as tmp:
        root = Path(tmp)
        script = _script(root)

        for label, content in CASES:
            target = root / "pg_hba.conf"
            target.write_text(content, encoding="utf-8")

            # (What the probe makes of this shape is asked of a real server
            # below — it reads PostgreSQL's parse now, not the file's text.)
            first = subprocess.run(["bash", str(script), str(target)], capture_output=True, text=True)
            after = target.read_text(encoding="utf-8")
            check(f"{label}: the step succeeds", first.returncode == 0, first.stderr)
            check(
                f"{label}: the role's trust rule is the one that is reached",
                _role_is_reached(after),
                after,
            )
            check(f"{label}: no blanket trust survives", not _has_blanket_trust(after), after)

            second = subprocess.run(["bash", str(script), str(target)], capture_output=True, text=True)
            check(
                f"{label}: re-running changes nothing",
                second.returncode == 0 and target.read_text(encoding="utf-8") == after,
                second.stderr,
            )

        # A file the step cannot rewrite must fail loudly, never silently. The
        # file's own mode is not enough: `sed -i` replaces it by renaming, so the
        # directory is what has to be read-only.
        locked = root / "locked"
        locked.mkdir()
        (locked / "pg_hba.conf").write_text(UBUNTU_DEFAULT, encoding="utf-8")
        locked.chmod(0o555)
        try:
            result = subprocess.run(
                ["bash", str(script), str(locked / "pg_hba.conf")], capture_output=True, text=True
            )
            check(
                "a pg_hba.conf that cannot be rewritten fails the step",
                result.returncode != 0,
                result.stdout + result.stderr,
            )
        finally:
            locked.chmod(0o755)

        # Rules this step cannot see one line at a time. It must refuse, not
        # narrow what it can see and report success.
        for label, content, word in (
            ("a record continued onto the next line",
             "local all postgres peer\nhost all all 127.0.0.1/32 \\\n    trust\n",
             "continuation"),
            ("rules pulled in from another file",
             "local all postgres peer\ninclude_dir conf.d\n",
             "include"),
        ):
            unseeable = root / "unseeable.conf"
            unseeable.write_text(content, encoding="utf-8")
            result = subprocess.run(
                ["bash", str(script), str(unseeable)], capture_output=True, text=True
            )
            check(
                f"{label}: the step refuses instead of narrowing what it can see",
                result.returncode != 0 and word in result.stderr,
                result.stdout + result.stderr,
            )
            check(
                f"{label}: the file is left untouched",
                unseeable.read_text(encoding="utf-8") == content,
                unseeable.read_text(encoding="utf-8"),
            )

        missing = subprocess.run(
            ["bash", str(script), str(root / "nope.conf")], capture_output=True, text=True
        )
        check(
            "a missing pg_hba.conf fails the step naming it",
            missing.returncode != 0 and "not found" in missing.stderr,
            missing.stderr,
        )

    _against_a_real_server(check)

    if failures:
        print("\n".join(["", "FAILED:"] + failures))
        return 1
    print("\nThe pg_hba rewriter behaves as documented.")
    return 0


def _against_a_real_server(check) -> None:
    """Ask PostgreSQL the same questions, in a cluster of our own.

    This is the oracle no reading of the file can replace: the server's own parse
    (`pg_hba_file_rules`) and a connection that either happens or does not.
    """
    bindir = _postgres_bindir()
    if bindir is None:
        print("skip  PostgreSQL binaries not found — the server-backed checks need initdb")
        return
    if os.geteuid() == 0:
        print("skip  running as root — initdb refuses, so the server-backed checks are skipped")
        return

    with tempfile.TemporaryDirectory(prefix="odwg-pghba-pg-") as tmp:
        root = Path(tmp)
        cluster = Cluster(root, bindir)
        try:
            # Inside the try: a start that fails *after* the postmaster came up
            # would otherwise leave it running over a deleted directory.
            try:
                cluster.start()
            except subprocess.CalledProcessError as error:
                print(f"skip  could not start a throwaway cluster: {error.stderr.strip()[:120]}")
                return
            script = _script(root)
            for label, content in CASES:
                # What the server says about the fixture, before anything is done.
                cluster.load(content)
                server_rules = cluster.rules()
                probed = _probe(cluster)
                check(
                    f"{label}: the probe reads the server the way the server reads the file",
                    probed is not None
                    and probed[0] == (pghba.blanket_trust(server_rules) is not None)
                    and probed[1] == pghba.role_is_reached(server_rules, ROLE),
                    f"probe={probed} server_blanket={pghba.blanket_trust(server_rules) is not None} "
                    f"server_reached={pghba.role_is_reached(server_rules, ROLE)}",
                )
                check(
                    f"{label}: PostgreSQL agrees there is a blanket trust"
                    if _has_blanket_trust(content)
                    else f"{label}: PostgreSQL agrees there is no blanket trust",
                    (pghba.blanket_trust(server_rules) is not None) == _has_blanket_trust(content),
                    f"server={pghba.blanket_trust(server_rules)} reading={_has_blanket_trust(content)}",
                )

                # And after the step has run over it.
                target = root / "pg_hba.conf"
                target.write_text(content, encoding="utf-8")
                subprocess.run(["bash", str(script), str(target)], capture_output=True, text=True)
                cluster.load(target.read_text(encoding="utf-8"))
                narrowed = cluster.rules()
                check(
                    f"{label}: PostgreSQL sees no rule trusting every role afterwards",
                    pghba.blanket_trust(narrowed) is None,
                    str(pghba.blanket_trust(narrowed)),
                )
                check(
                    f"{label}: PostgreSQL matches {ROLE} against the rule the step added",
                    pghba.role_is_reached(narrowed, ROLE),
                    "\n".join(str(rule) for rule in narrowed),
                )
                check(
                    f"{label}: {ROLE} really connects over TCP without a password",
                    cluster.role_can_connect_over_tcp(),
                    target.read_text(encoding="utf-8"),
                )

            _the_audit_step(check, cluster)
        finally:
            cluster.stop()


# What the plan's own verification step must accept and refuse. The file is put
# in front of a real server, because each of these is a state only the server
# knows about — the text says nothing about them.
AUDIT_CASES = [
    ("a rule the server cannot parse, so the reload was refused",
     "local all all trust\nhost all odoo 127.0.0.1/32 trust\n"
     "host all all 127.0.0.1/32 bogusmethod\n", True),
    ("a database and role literally named \"all\"",
     'local all all trust\nhost all odoo 127.0.0.1/32 trust\n'
     'host "all" "all" 127.0.0.1/32 trust\n', False),
    ("a trust rule naming its roles by pattern",
     'local all all trust\nhost all odoo 127.0.0.1/32 trust\n'
     'host all "/.*" 127.0.0.1/32 trust\n', True),
    ("a blanket trust the rewriter left behind",
     "local all all trust\nhost all odoo 127.0.0.1/32 trust\n"
     "host all all 127.0.0.1/32 trust\n", True),
    ("the role's own rule is hostnossl, so never consulted",
     "local all all trust\nhostnossl all odoo 127.0.0.1/32 trust\n"
     "host all all 127.0.0.1/32 scram-sha-256\n", True),
    ("a properly narrowed file",
     "local all all trust\nhost all odoo 127.0.0.1/32 trust\n"
     "host all all 127.0.0.1/32 scram-sha-256\n", False),
]


def _the_audit_step(check, cluster: Cluster) -> None:
    """The plan's own "ask PostgreSQL what rules it now has" step, run for real."""
    command = next(
        c.command for c in planners.plan_pg_hba_trust(ROLE) if "pg_hba_file_rules" in c.command
    )
    prefix = "sudo -u postgres psql"
    # Without this, a flag added to that command would make the replace miss and
    # the verifier would grade its cases against the host's own cluster.
    assert prefix in command, f"the audit step's psql prefix changed: {command}"
    audit = command.replace(
        prefix, f"{cluster.bin / 'psql'} -h {cluster.root} -p {cluster.port} -U postgres"
    )
    for label, content, should_fail in AUDIT_CASES:
        cluster.load(content)
        result = subprocess.run(["bash", "-c", audit], capture_output=True, text=True)
        check(
            f"the audit step {'refuses' if should_fail else 'accepts'}: {label}",
            (result.returncode != 0) == should_fail,
            f"exit={result.returncode} {result.stderr.strip()[:160]}",
        )


def _probe(cluster: Cluster) -> tuple[bool, bool] | None:
    """`system.pg_hba_loopback_state` against the throwaway cluster.

    Only the `sudo -n -u postgres psql` prefix is redirected, so the real query,
    the real parser and the real classification all run."""
    real_run = system.run
    prefix = "sudo -n -u postgres psql"
    replacement = f"{cluster.bin / 'psql'} -h {cluster.root} -U postgres"

    def redirected(command: str, check: bool = False):
        if prefix not in command:
            # Never let a probe that was meant for the throwaway cluster reach the
            # host's own: this redirect is string surgery, and adding a flag to
            # the real command once made it silently miss.
            raise AssertionError(f"probe command no longer starts with {prefix!r}: {command}")
        return real_run(command.replace(prefix, replacement), check=check)

    system.run = redirected  # type: ignore[assignment]
    try:
        return system.pg_hba_loopback_state(ROLE, port=cluster.port)
    finally:
        system.run = real_run


if __name__ == "__main__":
    raise SystemExit(main())
