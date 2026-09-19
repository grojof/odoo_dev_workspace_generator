#!/usr/bin/env python3
"""Execute the generated `pg_hba.conf` rewriter against real files.

`plan_pg_hba_trust` emits three chained `sed -ri` expressions that rewrite a
root-owned authentication file, with the development role interpolated into the
replacement text. The unit suite may not shell out (CLAUDE.md), so its only
assertion is on the plan's *text* — which is how a blanket `trust` written as
`localhost` rather than `127.0.0.1/32` once survived the narrowing while the
check reported `trust for odoo only`.

This renders the real command, replaces only its `SHOW hba_file;` lookup with a
fixture path, runs it over a set of `pg_hba.conf` shapes, and asserts the result
— and asserts the probe in `system.pg_hba_loopback_state` reads each shape the
same way the rewriter does.

    python tools/verify_pg_hba_trust.py

Host-only (needs bash and sed), no network, no PostgreSQL, nothing written
outside its temp directory. The rewriter's final connection check is the one
thing this cannot exercise: it needs a live server.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odoo_dwg import planners, system  # noqa: E402

ROLE = "odoo"
LOOKUP = 'PGHBA=$(sudo -u postgres psql -tAc "SHOW hba_file;")'

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

# The role's line is there, but a rule for every role above it decides the
# connection first, so it is never read.
SHADOWED_ROLE = """\
local   all             postgres                                peer
host    all             all             127.0.0.1/32            scram-sha-256
host    all             odoo            127.0.0.1/32            trust
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
]

ROLE_LINE = re.compile(
    rf"^\s*host(nossl)?\s+all\s+{ROLE}\s+\S+(\s+[0-9a-fA-F.:]+)?\s+trust(\s|$)", re.MULTILINE
)
BLANKET_TRUST = re.compile(
    r"^\s*host(nossl)?(\s+all){2}\s+\S+(\s+[0-9a-fA-F.:]+)?\s+trust(\s|$)",
    re.MULTILINE,
)


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

            # The probe must read the file the same way the rewriter treats it,
            # or `provision check` reports a state `provision apply` disagrees with.
            before = target.read_text(encoding="utf-8")
            probed = _probe(target)
            check(
                f"{label}: the probe and the file agree on the blanket trust",
                probed is not None and probed[0] == bool(BLANKET_TRUST.search(before)),
                f"probe={probed} file_has_blanket={bool(BLANKET_TRUST.search(before))}",
            )
            check(
                f"{label}: the probe and the file agree on whether the role's line is reached",
                probed is not None and probed[1] == _role_rule_wins(before),
                f"probe={probed} role_rule_reached={_role_rule_wins(before)}",
            )

            first = subprocess.run(["bash", str(script), str(target)], capture_output=True, text=True)
            after = target.read_text(encoding="utf-8")
            check(f"{label}: the step succeeds", first.returncode == 0, first.stderr)
            check(f"{label}: the role gets its loopback trust", bool(ROLE_LINE.search(after)), after)
            check(f"{label}: no blanket trust survives", not BLANKET_TRUST.search(after), after)
            check(
                f"{label}: the role's rule comes before any rule for all roles",
                _role_rule_wins(after),
                after,
            )

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

        missing = subprocess.run(
            ["bash", str(script), str(root / "nope.conf")], capture_output=True, text=True
        )
        check(
            "a missing pg_hba.conf fails the step naming it",
            missing.returncode != 0 and "not found" in missing.stderr,
            missing.stderr,
        )

    if failures:
        print("\n".join(["", "FAILED:"] + failures))
        return 1
    print("\nThe pg_hba rewriter behaves as documented.")
    return 0


def _probe(fixture: Path) -> tuple[bool, bool] | None:
    """`system.pg_hba_loopback_state` against a fixture: its only I/O is the
    `SHOW hba_file;` lookup and the read, so both are pointed at the file."""
    real_run, real_read = system.run, system.read_text

    class _Result:
        stdout = str(fixture)

    system.run = lambda *a, **k: _Result()  # type: ignore[assignment]
    system.read_text = lambda path: Path(path).read_text(encoding="utf-8")  # type: ignore[assignment]
    try:
        return system.pg_hba_loopback_state(ROLE)
    finally:
        system.run, system.read_text = real_run, real_read


def _role_rule_wins(text: str) -> bool:
    """pg_hba is first-match-wins: the role's own rule must precede any `all`
    rule that would match the same loopback connection."""
    for line in text.splitlines():
        if ROLE_LINE.match(line):
            return True
        if re.match(r"^\s*host(nossl)?(\s+all){2}\s", line):
            return False
    return False


if __name__ == "__main__":
    raise SystemExit(main())
