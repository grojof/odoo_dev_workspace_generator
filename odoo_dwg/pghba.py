"""PostgreSQL host-based authentication rules, as the server itself reports them.

`pg_hba.conf` is PostgreSQL's format, and four audit rounds established that
re-implementing its parser to answer one question loses: five TCP connection
types, two address forms plus keyword addresses, per-rule options, comma-separated
and regex-valued fields, `@file` lists, line continuations and `include*`. The
server exposes the parsed result in ``pg_hba_file_rules``; this module turns that
query's output into records and answers the two questions ``provision`` asks.

Pure: the query itself lives in ``system``. See
``openspec/changes/archive/*-read-pg-hba-from-the-server/design.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

# The columns SELECTed, in order, tab-separated (``psql -tAF'\t'``).
COLUMNS = (
    "type",
    "database",
    "user_name",
    "address",
    "netmask",
    "auth_method",
    "file_name",
    "line_number",
    "error",
)


@dataclass(frozen=True)
class Rule:
    """One effective rule. ``databases``/``users`` arrive as arrays, so a
    comma-separated field is already split, and ``file`` names the file the rule
    came from — an ``include_dir`` member, when that is where it lives."""

    type: str
    databases: tuple[str, ...]
    users: tuple[str, ...]
    address: str
    netmask: str
    method: str
    file: str
    line: int
    error: str

    @property
    def is_tcp(self) -> bool:
        """Every `host…` type: plain, `hostssl`, `hostnossl`, `hostgssenc`,
        `hostnogssenc`. A `local` rule is the unix socket, out of scope here."""
        return self.type.startswith("host")


def parse_rules(output: str) -> list[Rule]:
    """Records from the query's tab-separated output. A row that cannot be read
    is skipped rather than guessed at; a row carrying an ``error`` is kept, so a
    caller can refuse to judge a file the server could not parse."""
    rules: list[Rule] = []
    for raw in output.splitlines():
        if not raw.strip():
            continue
        fields = raw.split("\t")
        if len(fields) != len(COLUMNS):
            continue
        type_, databases, users, address, netmask, method, file_name, line, error = fields
        rules.append(
            Rule(
                type=type_,
                databases=tuple(part for part in databases.split(",") if part),
                users=tuple(part for part in users.split(",") if part),
                address=address,
                netmask=netmask,
                method=method,
                file=file_name,
                line=int(line) if line.isdigit() else 0,
                error=error,
            )
        )
    return rules


def unreadable(rules: list[Rule]) -> Rule | None:
    """The first rule the server itself could not parse, if any. A file with one
    is not a file to draw conclusions from."""
    return next((rule for rule in rules if rule.error), None)


def blanket_trust(rules: list[Rule]) -> Rule | None:
    """The first TCP rule trusting *every* role, whatever address it names.

    The address is deliberately not interpreted: `all`, `0.0.0.0/0` and
    `127.0.0.0/8` all contain loopback without naming it, and a rule trusting
    every role on any address is not something this tool leaves behind.
    """
    return next(
        (
            rule
            for rule in rules
            if rule.is_tcp and "all" in rule.databases and "all" in rule.users
            and rule.method == "trust"
        ),
        None,
    )


def role_is_reached(rules: list[Rule], role: str) -> bool:
    """Whether ``role``'s own trust rule is the one a TCP connection matches.

    `pg_hba` is first-match-wins, so a rule below one that already matches the
    same connection is never read. Any earlier TCP rule covering this role counts
    as a match, whatever its address: assuming otherwise is how a rule was read as
    reached when it was not, and the cost of being strict is one extra line.
    """
    for rule in rules:
        if not rule.is_tcp:
            continue
        if role not in rule.users and "all" not in rule.users:
            continue
        return role in rule.users and rule.method == "trust" and "all" in rule.databases
    return False


def quotes_a_field(line: str) -> bool:
    """Whether a rule's own text quotes one of its fields.

    ``host "all" "all" 127.0.0.1/32 trust`` is a rule for a database and a role
    *named* `all`, which PostgreSQL does not treat as the keyword — but the view
    reports both as `all`, indistinguishable from it. The raw line is the only
    place that distinction survives, so a quoted rule is never classified as
    blanket.
    """
    return '"' in line.split("#", 1)[0]
