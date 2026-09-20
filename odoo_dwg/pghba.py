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
    """The first TCP rule trusting *every* role, on any database and whatever
    address it names.

    The address is deliberately not interpreted: `all`, `0.0.0.0/0` and
    `127.0.0.0/8` all contain loopback without naming it, and a rule trusting
    every role on any address is not something this tool leaves behind.

    Neither is the database: ``host mydb all 127.0.0.1/32 trust`` lets any local
    user connect to `mydb` as `postgres`, and a superuser in one database runs
    programs on the host. The database bounds *which* database is exposed, never
    *whether* one is.
    """
    return next(
        (
            rule
            for rule in rules
            if rule.is_tcp and "all" in rule.users and rule.method == "trust"
        ),
        None,
    )


def names_roles_by_pattern(rules: list[Rule]) -> Rule | None:
    """The first TCP trust rule naming its roles by regex (`/…`) or group (`+…`).

    Those reach every member without spelling `all`, and the view reports the
    field verbatim, so whether such a rule trusts everyone cannot be told from
    here. Like ``unreadable``, it is a reason to say "unknown" rather than "fine".
    """
    return next(
        (
            rule
            for rule in rules
            if rule.is_tcp and rule.method == "trust"
            and any(user.startswith(("/", "+")) for user in rule.users)
        ),
        None,
    )


def role_is_reached(rules: list[Rule], role: str) -> bool:
    """Whether ``role``'s own trust rule is the one a TCP connection matches.

    `pg_hba` is first-match-wins, so a rule below one that already matches the
    same connection is never read. Any earlier TCP rule covering this role counts
    as a match, whatever its address: assuming otherwise is how a rule was read as
    reached when it was not, and the cost of being strict is one extra line.

    Only a plain ``host`` rule *reaches* it. The supported host runs with
    ``ssl = on`` and clients prefer TLS, so a ``hostnossl`` rule is never
    consulted — counting one as reached would report a host as narrowed where the
    role cannot connect at all.
    """
    for rule in rules:
        if not rule.is_tcp:
            continue
        if role not in rule.users and "all" not in rule.users:
            continue
        return (
            rule.type == "host"
            and role in rule.users
            and rule.method == "trust"
            and "all" in rule.databases
        )
    return False


# What `hba.c` counts as a blank between fields. Python's ``str.isspace`` is
# wider (NBSP, form feed, U+2000…), and a wider notion ends a field the server
# keeps open.
_BLANK = " \t\r"


def _scan_fields(text: str) -> list[list[tuple[str, bool]]]:
    """A rule's fields, each split into its comma-separated elements.

    Each element is ``(text, was_quoted)``. This is `pg_hba`'s own tokenization
    as far as it matters here: whitespace separates fields unless it sits inside
    double quotes, `""` is an escaped quote, and a field may be a comma list.
    """
    fields: list[list[tuple[str, bool]]] = []
    index, end = 0, len(text)
    while index < end:
        if text[index] in _BLANK:
            index += 1
            continue
        elements: list[tuple[str, bool]] = []
        current, quoted = "", False
        while index < end:
            char = text[index]
            if char == '"':
                quoted = True
                index += 1
                while index < end:
                    if text[index] == '"':
                        if index + 1 < end and text[index + 1] == '"':
                            current += '"'
                            index += 2
                            continue
                        index += 1
                        break
                    current += text[index]
                    index += 1
                continue
            if char in _BLANK:
                break
            if char == ",":
                elements.append((current, quoted))
                current, quoted = "", False
                index += 1
                continue
            current += char
            index += 1
        elements.append((current, quoted))
        fields.append(elements)
    return fields


def role_elements(line: str) -> tuple[str, ...] | None:
    """The roles a TCP rule's own text names, or None when the line is not one.

    The view cannot tell the keyword `all` from a role *named* `all`, and the
    line can, so an element that is a quoted ``all`` comes back as ``"all"`` —
    quotes included — which is equal to no role and not to the keyword. Every
    other element is its plain text, since quoting a name changes nothing.

    The field is read as the list it may be: PostgreSQL matches the keyword
    anywhere in ``all,bob``, so reading only a bare ``all`` called that rule
    narrow while the server let every role in.

    None is also the answer whenever the *view* knows more than the line, and
    the line must not override it. The line knows one thing the view lost —
    whether `all` was quoted — and nothing else, so a record continued onto the
    next line, or one naming its roles from a file (``@admins``, which the server
    has already expanded), is left to the server's reading.
    """
    body = line.split("#", 1)[0]
    if body.rstrip().endswith("\\"):
        return None
    fields = _scan_fields(body)
    if len(fields) < 3 or not fields[0][0][0].lower().startswith("host"):
        return None
    if any(text.startswith("@") for text, _quoted in fields[2]):
        return None
    return tuple(
        '"all"' if quoted and text == "all" else text for text, quoted in fields[2]
    )


def role_field_is_keyword_all(line: str) -> bool:
    """Whether a rule's own text names *every role*, rather than one named `all`."""
    return "all" in (role_elements(line) or ())
