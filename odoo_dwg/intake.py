"""Taking in a copy of a client's production: what the client runs, found out.

A client hands over a database dump, an archive of the add-ons their server
loads, and its configuration. Before a single step of a migration, the tool has
to know what is in them: whether the dump restored whole, which directory each
installed module loads from, whether production runs code its repository does
not hold, and which Odoo core — official, OCA/OCB, or patched — at which
commit. The first intake was done by hand and walked into a trap at almost
every one of those questions; each answer here is the one that trap taught.

Pure: parsing, classification and matching. Running ``pg_restore``, ``git`` and
``tar`` is ``system``'s job; the workflow wires them.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from .models import MODULE_NAME_RE

INTAKE_SCHEMA = 1
FLAVOURS = {
    "odoo": "https://github.com/odoo/odoo",
    "ocb": "https://github.com/OCA/OCB",
}
MANIFESTS = ("__manifest__.py", "__openerp__.py")

_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]+$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_PIP_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class IntakeError(ValueError):
    """An intake record, or an input, that cannot be used — with every reason."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


# --- the record ------------------------------------------------------------------------

@dataclass(frozen=True)
class Core:
    """The Odoo core the client runs."""

    flavour: str          # "odoo" | "ocb"
    commit: str           # 40 hex characters

    @property
    def url(self) -> str:
        return FLAVOURS[self.flavour]


@dataclass(frozen=True)
class IntakeRecord:
    """What an intake established, kept in ``intake.json`` at the environment's root.

    ``archive_root`` is relative to the environment root (``client-src/<top>``);
    ``addons_dirs`` are relative to it, in the client's ``addons_path`` order,
    without the core's directories: the core comes from ``core``."""

    reference_database: str
    reader_role: str = ""
    archive_root: str = ""
    addons_dirs: tuple[str, ...] = ()
    core: Core | None = None
    core_dir: str = ""            # the archive's core root (holds ``odoo/addons``), relative
    python_deps: tuple[str, ...] = ()   # pip names the installed modules' manifests need


def parse_intake(text: str) -> IntakeRecord:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise IntakeError([f"not valid JSON: {error}"]) from None
    if not isinstance(raw, dict):
        raise IntakeError(["expected a JSON object"])
    if raw.get("schema") != INTAKE_SCHEMA:
        raise IntakeError([f"schema version {raw.get('schema')!r} is not one this tool reads "
                           f"(it reads {INTAKE_SCHEMA})"])
    problems: list[str] = []
    ref = raw.get("reference_database")
    if not (isinstance(ref, str) and _NAME_RE.fullmatch(ref)):
        problems.append(f"reference_database: not a database name: {ref!r}")
    role = raw.get("reader_role", "")
    if role and not (isinstance(role, str) and _NAME_RE.fullmatch(role)):
        problems.append(f"reader_role: not a role name: {role!r}")
    root = raw.get("archive_root", "")
    if not isinstance(root, str) or root.startswith("/") or ".." in root.split("/"):
        problems.append(f"archive_root: expected a path under the environment, got {root!r}")
    dirs = raw.get("addons_dirs", [])
    if not (isinstance(dirs, list) and all(
            isinstance(d, str) and d and not d.startswith("/") and ".." not in d.split("/")
            for d in dirs)):
        problems.append("addons_dirs: expected relative paths inside the archive")
        dirs = []
    core = None
    if raw.get("core") is not None:
        c = raw["core"]
        if not (isinstance(c, dict) and c.get("flavour") in FLAVOURS
                and isinstance(c.get("commit"), str) and _COMMIT_RE.fullmatch(c["commit"])):
            problems.append(f"core: expected flavour in {sorted(FLAVOURS)} and a 40-hex commit, "
                            f"got {c!r}")
        else:
            core = Core(c["flavour"], c["commit"])
    deps = raw.get("python_deps", [])
    if not (isinstance(deps, list) and all(isinstance(d, str) and _PIP_RE.fullmatch(d)
                                           for d in deps)):
        problems.append(f"python_deps: expected pip distribution names, got {deps!r}")
        deps = []
    core_dir = raw.get("core_dir", "")
    if not isinstance(core_dir, str) or core_dir.startswith("/") or ".." in core_dir.split("/"):
        problems.append(f"core_dir: expected a path inside the archive, got {core_dir!r}")
    if problems:
        raise IntakeError(problems)
    return IntakeRecord(str(ref), str(role), str(root), tuple(dirs), core, str(core_dir),
                        tuple(deps))


def dump_intake(record: IntakeRecord) -> str:
    raw = {
        "schema": INTAKE_SCHEMA,
        "reference_database": record.reference_database,
        "reader_role": record.reader_role,
        "archive_root": record.archive_root,
        "addons_dirs": list(record.addons_dirs),
        "core_dir": record.core_dir,
        "python_deps": list(record.python_deps),
        "core": ({"flavour": record.core.flavour, "url": record.core.url,
                  "commit": record.core.commit} if record.core else None),
    }
    return json.dumps(raw, indent=2) + "\n"


def redact_url(url: str) -> str:
    """A remote URL without the credentials a private one may carry
    (``https://user:token@host/…``): the client's remotes are recorded to say
    where code came from, never to be used, and a token must not reach a ledger."""
    return re.sub(r"^([a-z][a-z0-9+.-]*://)[^/@]*@", r"\1", url.strip())


# --- restoring the dump ----------------------------------------------------------------

@dataclass(frozen=True)
class RestoreErrorClass:
    """A ``pg_restore`` error known to lose no data, with why and where that is shown."""

    id: str
    pattern: str
    reason: str
    source: str


KNOWN_RESTORE_ERRORS: tuple[RestoreErrorClass, ...] = (
    RestoreErrorClass(
        "array-cat-anyarray-aggregate",
        r"CREATE AGGREGATE .*array_cat|function array_cat\(anyarray, anyarray\) does not exist",
        "An aggregate built on array_cat(anyarray): PostgreSQL 14 changed array_cat to "
        "anycompatiblearray, so the definition no longer compiles. An aggregate stores no data, "
        "and code that uses it recreates it when it runs; on PostgreSQL 14+ that code fails at "
        "that moment, not at restore.",
        "PostgreSQL 14.0 release notes, Migration to Version 14: user-defined objects that "
        "reference array_cat() and similar with anyarray must be recreated "
        "(https://www.postgresql.org/docs/release/14.0/)",
    ),
)


@dataclass(frozen=True)
class RestoreError:
    message: str
    command: str = ""


def parse_restore_errors(stderr: str) -> list[RestoreError]:
    """Every ``pg_restore: error:`` with the ``Command was:`` that caused it."""
    errors: list[RestoreError] = []
    lines = stderr.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("pg_restore: error:"):
            message = line.removeprefix("pg_restore: error:").strip()
            command: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("pg_restore:"):
                text = lines[i]
                if text.startswith("Command was:"):
                    command.append(text.removeprefix("Command was:").strip())
                elif command:
                    command.append(text.strip())
                i += 1
            errors.append(RestoreError(message, " ".join(c for c in command if c)))
            continue
        i += 1
    return errors


def classify(errors: list[RestoreError]) -> list[tuple[RestoreError, RestoreErrorClass | None]]:
    out = []
    for error in errors:
        text = f"{error.message} {error.command}"
        known = next((k for k in KNOWN_RESTORE_ERRORS if re.search(k.pattern, text, re.S)), None)
        out.append((error, known))
    return out


# --- the reader role -------------------------------------------------------------------

#: Column names that hold secrets, whatever the table and version: passwords,
#: keys, tokens, and attachment contents. A foreign key (``*_id``) is not one.
SECRET_COLUMN_RE = re.compile(
    r"passw|secret|token|private_key|public_key|api_?key|smtp_pass|totp|^db_datas$|"
    r"^index_content$")
#: Secrets whose column name says nothing: every system parameter's value.
SECRET_COLUMNS: tuple[tuple[str, str], ...] = (("ir_config_parameter", "value"),)


def is_secret(table: str, column: str) -> bool:
    if (table, column) in SECRET_COLUMNS:
        return True
    return bool(SECRET_COLUMN_RE.search(column)) and not re.search(r"_ids?$", column)


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def reader_role_sql(role: str, database: str, columns: list[tuple[str, str]]) -> str:
    """Grants for a role that reads everything but secrets, as the database owner.

    ``columns`` is every ``(table, column)`` of the schema, read from
    ``pg_attribute`` — not ``information_schema``, which lists only what the
    connected role may read. A table with a secret column is granted column by
    column, so ``SELECT *`` on it fails rather than leaking.

    Sequences are readable (``SELECT``, not ``USAGE``): a wizard leaves no rows,
    so its id sequence is the only trace that anyone ever opened it."""
    if not (_NAME_RE.fullmatch(role) and _NAME_RE.fullmatch(database)):
        raise IntakeError([f"not a role or database name: {role!r}, {database!r}"])
    r = _ident(role)
    lines = [
        f"REVOKE TEMPORARY ON DATABASE {_ident(database)} FROM PUBLIC;",
        f"GRANT CONNECT ON DATABASE {_ident(database)} TO {r};",
        f"GRANT USAGE ON SCHEMA public TO {r};",
        f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {r};",
        f"GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO {r};",
    ]
    by_table: dict[str, list[str]] = {}
    for table, column in columns:
        by_table.setdefault(table, []).append(column)
    for table in sorted(by_table):
        cols = by_table[table]
        hidden = [c for c in cols if is_secret(table, c)]
        if not hidden:
            continue
        visible = [c for c in cols if c not in hidden]
        lines.append(f"REVOKE SELECT ON public.{_ident(table)} FROM {r};")
        if visible:
            lines.append(f"GRANT SELECT ({', '.join(_ident(c) for c in visible)}) "
                         f"ON public.{_ident(table)} TO {r};")
    return "\n".join(lines) + "\n"


def hidden_columns(columns: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return sorted((t, c) for t, c in columns if is_secret(t, c))


# --- the add-ons archive ---------------------------------------------------------------

def conf_addons_path(conf_text: str) -> list[str]:
    """The ``addons_path`` entries of an ``odoo.conf``, in order."""
    for line in conf_text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == "addons_path":
            return [p.strip().rstrip("/") for p in value.split(",") if p.strip()]
    return []


@dataclass(frozen=True)
class ArchiveLayout:
    """The client's ``addons_path`` mapped into the unpacked archive."""

    dirs: tuple[str, ...]             # every entry, relative to the archive root, in order
    missing: tuple[str, ...]          # entries of the conf found nowhere in the archive
    core_root: str | None             # the directory holding ``odoo/addons`` (the core)
    core_dirs: tuple[str, ...]        # the core's entries (``<root>/odoo/addons``, ``<root>/addons``)

    @property
    def client_dirs(self) -> tuple[str, ...]:
        return tuple(d for d in self.dirs if d not in self.core_dirs)


def archive_layout(entries: list[str], archive_dirs: set[str],
                   has_base: set[str]) -> ArchiveLayout:
    """Map server paths onto the archive by their common prefix.

    ``archive_dirs`` are the directories inside the archive root; ``has_base``
    those holding ``base`` with a manifest, which marks the core's
    ``odoo/addons``."""
    if not entries:
        raise IntakeError(["the configuration has no addons_path"])
    parts = [e.strip("/").split("/") for e in entries]
    common = 0
    while all(len(p) > common for p in parts) and len({p[common] for p in parts}) == 1:
        common += 1
    mapped, missing = [], []
    for p, entry in zip(parts, entries, strict=True):
        rel = "/".join(p[common:])
        (mapped if rel in archive_dirs else missing).append(rel if rel in archive_dirs else entry)
    core_root = next((d[: -len("odoo/addons")].rstrip("/") for d in mapped
                      if d.endswith("odoo/addons") and d in has_base), None)
    core_dirs: tuple[str, ...] = ()
    if core_root is not None:
        prefix = f"{core_root}/" if core_root else ""
        core_dirs = tuple(d for d in mapped if d in (f"{prefix}odoo/addons", f"{prefix}addons"))
    return ArchiveLayout(tuple(mapped), tuple(missing), core_root, core_dirs)


@dataclass(frozen=True)
class ModuleMap:
    loads_from: dict[str, str] = field(default_factory=dict)     # module -> directory
    duplicates: dict[str, list[str]] = field(default_factory=dict)
    legacy_manifest: tuple[str, ...] = ()
    installed_without_code: tuple[str, ...] = ()


def classify_modules(listing: list[tuple[str, str, str]], installed: set[str]) -> ModuleMap:
    """``listing`` is ``(directory, module, manifest file)`` in ``addons_path`` order;
    the first directory holding a module is the one Odoo loads it from."""
    loads: dict[str, str] = {}
    seen: dict[str, list[str]] = {}
    legacy = []
    for directory, module, manifest in listing:
        seen.setdefault(module, []).append(directory)
        if module not in loads:
            loads[module] = directory
            if manifest == "__openerp__.py":
                legacy.append(module)
    duplicates = {m: d for m, d in seen.items() if len(d) > 1}
    return ModuleMap(loads, duplicates, tuple(sorted(legacy)),
                     tuple(sorted(installed - set(loads))))


#: Import names whose pip distribution is called something else. A manifest's
#: ``external_dependencies['python']`` lists what the module *imports*; pip installs
#: distributions. Any name not here is taken as its own distribution name.
PIP_NAMES: dict[str, str] = {
    "OpenSSL": "pyOpenSSL",
    "dateutil": "python-dateutil",
    "yaml": "PyYAML",
    "PIL": "Pillow",
    "Crypto": "pycryptodome",
    "cv2": "opencv-python",
    "ldap": "python-ldap",
    "magic": "python-magic",
    "serial": "pyserial",
    "usb": "pyusb",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "dns": "dnspython",
    "jwt": "PyJWT",
    "bs4": "beautifulsoup4",
    "slugify": "python-slugify",
    "stdnum": "python-stdnum",
    "barcode": "python-barcode",
    "Levenshtein": "python-Levenshtein",
    "sklearn": "scikit-learn",
}


def manifest_python_imports(text: str) -> list[str] | None:
    """The Python imports a manifest declares, or None when it cannot be read.

    A manifest is a dict literal, read with ``ast.literal_eval`` — never executed."""
    import ast

    try:
        manifest = ast.literal_eval(text)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None
    if not isinstance(manifest, dict):
        return None
    external = manifest.get("external_dependencies") or {}
    names = external.get("python", []) if isinstance(external, dict) else []
    return [n for n in names if isinstance(n, str)]


def pip_names(imports: list[str]) -> tuple[str, ...]:
    """Pip distribution names for these imports, deduplicated, sorted."""
    out = {PIP_NAMES.get(name, name) for name in imports}
    return tuple(sorted((n for n in out if _PIP_RE.fullmatch(n)), key=str.lower))


# --- identifying the core --------------------------------------------------------------

def git_blob_id(data: bytes) -> str:
    """What ``git hash-object`` answers for this content."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()  # noqa: S324 — git's id


def parse_raw_log(text: str) -> dict[tuple[str, str], str]:
    """``{(path, blob): first date}`` from ``git log --raw --no-abbrev --format=@%H %cs``.

    Split on the tab between the status and the path — splitting on whitespace
    took a field for the path and matched nothing. Merge commits contribute their
    lines too (``--diff-merges=separate``), because a version a merge produced is a
    version the branch had."""
    found: dict[tuple[str, str], str] = {}
    when = ""
    for line in text.splitlines():
        if line.startswith("@"):
            parts = line[1:].split()
            when = parts[1] if len(parts) > 1 else ""
            continue
        if not line.startswith(":") or "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        fields = meta.split()
        if len(fields) < 5:
            continue
        blob = fields[3]
        key = (path, blob)
        if key not in found or (when and when < found[key]):
            found[key] = when
    return found


def parse_ls_tree(text: str) -> dict[str, str]:
    """``{path: blob}`` from ``git ls-tree -r``."""
    tree = {}
    for line in text.splitlines():
        meta, sep, path = line.partition("\t")
        fields = meta.split()
        if sep and len(fields) == 3 and fields[1] == "blob":
            tree[path] = fields[2]
    return tree


def _ignored(path: str) -> bool:
    return path.endswith((".pyc", ".pyo")) or "/__pycache__/" in f"/{path}"


@dataclass(frozen=True)
class CoreVerdict:
    flavour: str                      # "odoo" | "ocb" | "patched" | "unidentified"
    commit: str                       # the closest commit ("" when there is none)
    differing: tuple[str, ...]        # files differing from that commit (client has both)
    patched: tuple[str, ...]          # differing files no history of either flavour has
    client_only: tuple[str, ...]      # files only the client has (not in that commit)


def core_identity(client: dict[str, str], flavour: str, commit: str, tree: dict[str, str],
                  histories: dict[str, dict[tuple[str, str], str]]) -> CoreVerdict:
    """What the client's core is, given the closest commit found by comparing trees.

    The comparison is against that commit, not the branch head: a core years
    behind the head differs from it in thousands of files (translations first),
    and walking the history of each of them took longer than any operator waits.
    Only the files that still differ from the closest commit are looked up in the
    histories: one found there is an older or newer version the branch had; one
    found nowhere is a local patch. A file only the client has is set apart."""
    client = {p: b for p, b in client.items() if not _ignored(p)}
    tree = {p: b for p, b in tree.items() if not _ignored(p)}
    differing = tuple(sorted(p for p, b in client.items() if p in tree and tree[p] != b))
    client_only = tuple(sorted(p for p in client if p not in tree))
    patched = tuple(p for p in differing
                    if not any((p, client[p]) in h for h in histories.values()))
    verdict = flavour if not patched else "patched"
    if not commit:
        verdict = "unidentified"
    return CoreVerdict(verdict, commit, differing, patched, client_only)


def sample(commits: list[str], count: int) -> list[str]:
    """About ``count`` commits spread evenly over the list, first and last included."""
    if len(commits) <= count:
        return list(commits)
    step = (len(commits) - 1) / (count - 1)
    return list(dict.fromkeys(commits[round(i * step)] for i in range(count)))


@dataclass(frozen=True)
class CommitMatch:
    commit: str
    differences: int
    client_only: tuple[str, ...]


def best_commit(client: dict[str, str],
                trees: list[tuple[str, dict[str, str]]]) -> CommitMatch | None:
    """The commit whose tree differs least from the client's core.

    Every file counts, on both sides: one the commit has differently or the client
    lacks, and one only the client has. Not counting the client's own files once
    made a 2006 commit — whose tree had no ``addons/`` of that shape at all — a
    perfect match. The client's own files are still reported apart (a stray
    backup is not a difference in Odoo); they only raise the true commit's count
    by their number. Compiled files are ignored on both sides."""
    client = {p: b for p, b in client.items() if not _ignored(p)}
    best: CommitMatch | None = None
    for commit, tree in trees:
        tree = {p: b for p, b in tree.items() if not _ignored(p)}
        only = tuple(sorted(p for p in client if p not in tree))
        diff = sum(1 for p, b in tree.items() if client.get(p) != b) + len(only)
        if best is None or diff < best.differences:
            best = CommitMatch(commit, diff, only)
    return best


# --- surveying what the copy can act on -------------------------------------------------

#: Read-only queries of the survey. Each names only columns every version from 12.0
#: to 18.0 has; the workflow runs a query only where its table exists.
SURVEY_SQL = {
    "crons": ("SELECT coalesce(cron_name, ''), interval_number || ' ' || interval_type, "
              "to_char(nextcall, 'YYYY-MM-DD HH24:MI'), "
              "greatest(0, floor(extract(epoch FROM now() - nextcall) / 86400))::int "
              "FROM ir_cron WHERE active ORDER BY nextcall"),
    "queue": ("SELECT coalesce(channel, ''), state, count(*) FROM queue_job "
              "GROUP BY 1, 2 ORDER BY 1, 2"),
    "mail": ("SELECT state, count(*), coalesce(min(create_date)::date::text, ''), "
             "coalesce(max(create_date)::date::text, '') FROM mail_mail GROUP BY 1 ORDER BY 1"),
}
SURVEY_TABLES = {"crons": "ir_cron", "queue": "queue_job", "mail": "mail_mail"}


@dataclass(frozen=True)
class MailQueue:
    state: str
    count: int
    first: str
    last: str


def read_mail_queue(rows: list[list[str]]) -> list[MailQueue]:
    out = []
    for row in rows:
        if len(row) >= 4 and row[1].isdigit():
            out.append(MailQueue(row[0], int(row[1]), row[2], row[3]))
    return out


def overdue_crons(rows: list[list[str]]) -> list[list[str]]:
    """``[name, every, next call, days overdue]`` for the active crons past their call."""
    return [row[:4] for row in rows if len(row) >= 4 and row[3].isdigit() and int(row[3]) >= 0]


# --- modules along the chain ----------------------------------------------------------

_OCA_REMOTE_RE = re.compile(r"github\.com[:/]OCA/([A-Za-z0-9._-]+?)(?:\.git)?/?$")


def oca_repo(remote: str) -> str | None:
    """The OCA repository a remote URL names, or None when it is not OCA's."""
    match = _OCA_REMOTE_RE.search(remote.strip())
    return match.group(1) if match else None


def module_origin(directory: str, core_dirs: set[str], remotes: dict[str, str]) -> str:
    """``odoo`` from the core, ``oca`` from an OCA repository, ``custom`` otherwise."""
    if directory in core_dirs:
        return "odoo"
    return "oca" if oca_repo(remotes.get(directory, "")) else "custom"


@dataclass(frozen=True)
class Availability:
    module: str
    origin: str                      # "odoo" | "oca" | "custom"
    source_repo: str                 # the OCA repository at the source version, or ""
    names: tuple[str, ...]           # the name looked for at each step
    where: tuple[str, ...]           # "core", an OCA repository, "MISSING" or "port"
    merged_at: str = ""

    @property
    def gaps(self) -> tuple[int, ...]:
        return tuple(i for i, w in enumerate(self.where) if w == "MISSING")

    @property
    def moved(self) -> bool:
        return bool(self.source_repo) and any(
            w not in (self.source_repo, "MISSING", "core") for w in self.where)


def availability(installed: dict[str, tuple[str, str]], fates: list, steps: list[str],
                 found: dict[str, dict[str, str]]) -> list[Availability]:
    """Where each installed module's code is at each step, following its fate.

    ``installed`` is ``{module: (origin, source repository)}``; ``fates`` are
    ``preflight.ModuleFate``; ``found`` is ``{step: {module name: "core" | repo}}``.
    A merged module is looked for under its successor's name from the step of the
    merge; a custom module is not looked for — it is ported, not found."""
    hops: dict[str, list] = {}
    for fate in fates:
        if fate.kind in ("renamed", "merged"):
            hops.setdefault(fate.module, []).append(fate)
    rows = []
    for module, (origin, repo) in sorted(installed.items()):
        if origin == "custom":
            rows.append(Availability(module, origin, "", tuple(module for _ in steps),
                                     tuple("port" for _ in steps)))
            continue
        name, merged_at, names, where = module, "", [], []
        for step in steps:
            for hop in hops.get(module, []):
                if hop.version == step:
                    name = hop.successor
                    if hop.kind == "merged" and not merged_at:
                        merged_at = step
            names.append(name)
            where.append(found.get(step, {}).get(name, "MISSING"))
        rows.append(Availability(module, origin, repo, tuple(names), tuple(where), merged_at))
    return rows


# --- the client's own code, scanned ---------------------------------------------------

#: ``(name, pattern, control)``: each pattern must match its control line before any
#: scan is believed. A scan that found nothing because its pattern was broken would
#: read exactly like a clean one.
NETWORK_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("requests", r"\brequests\.(get|post|put|patch|delete|head|request|Session)\b",
     "r = requests.post(url, data=payload)"),
    ("urllib", r"\burllib(\.request|2)?\b", "from urllib.request import urlopen"),
    ("http.client", r"\bhttp\.client\b|\bhttplib\b", "import http.client"),
    ("smtplib", r"\bsmtplib\b", "server = smtplib.SMTP(host)"),
    ("ftplib", r"\bftplib\b", "from ftplib import FTP"),
    ("paramiko", r"\bparamiko\b|\bpysftp\b", "client = paramiko.SSHClient()"),
    ("soap", r"\bzeep\b|\bsuds\b", "from zeep import Client"),
    ("socket", r"\bsocket\.(socket|create_connection)\b", "s = socket.create_connection(addr)"),
    ("subprocess", r"\bsubprocess\b|\bos\.(system|popen)\b", "subprocess.run(['ls'])"),
    ("rpc", r"\bxmlrpc\b|\bjsonrpc\b", "import xmlrpc.client"),
    ("job-queue", r"\.with_delay\(", "record.with_delay().send()"),
    ("iap", r"\biap_jsonrpc\b|\biap_tools\b", "iap_tools.iap_jsonrpc(url, params=p)"),
)


def scanner_self_test() -> list[str]:
    """The patterns that fail to match their own control line. Empty means working."""
    return [name for name, pattern, control in NETWORK_PATTERNS
            if not re.search(pattern, control)]


def scan_skipped(relpath: str) -> bool:
    """Tests reach mocks and migrations run once: not what the module does."""
    parts = relpath.split("/")
    return "tests" in parts or "migrations" in parts


def scan_source(text: str) -> list[tuple[int, str, str]]:
    """``(line number, pattern name, line)`` for every line reading as a network call."""
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for name, pattern, _control in NETWORK_PATTERNS:
            if re.search(pattern, line):
                hits.append((number, name, stripped[:160]))
                break
    return hits


def parse_repo_page(text: str) -> list[str] | None:
    """Repository names from one page of GitHub's organisation listing, or None."""
    try:
        page = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(page, list):
        return None
    return [r["name"] for r in page if isinstance(r, dict) and isinstance(r.get("name"), str)
            and _NAME_RE.fullmatch(r["name"])]


# --- rehearsing an uninstall -----------------------------------------------------------

#: Exact row counts of every table: the statistics estimate is refreshed by
#: ANALYZE, not by the deletes an uninstall makes. One statement, so no table
#: name ever reaches the shell.
UNINSTALL_ROWS_SQL = (
    "SELECT c.relname, (xpath('/row/n/text()', query_to_xml(format("
    "'SELECT count(*) AS n FROM public.%I', c.relname), false, true, '')))[1]::text "
    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 1"
)
UNINSTALL_COLUMNS_SQL = (
    "SELECT c.relname, a.attname FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' "
    "AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped ORDER BY 1, 2"
)
UNINSTALL_INSTALLED_SQL = (
    "SELECT name FROM ir_module_module WHERE state IN ('installed', 'to upgrade', 'to remove') "
    "ORDER BY 1"
)
UNINSTALL_TRANSIENT_SQL = "SELECT model FROM ir_model WHERE transient ORDER BY 1"
UNINSTALL_RELATED_SQL = (
    "SELECT model, name FROM ir_model_fields WHERE store AND coalesce(related, '') <> '' "
    "ORDER BY 1, 2"
)

#: The registry's own tables. Other ir_* tables (attachments, crons, parameters,
#: sequences, properties) are the client's configuration or data.
UNINSTALL_METADATA = (
    "ir_model", "ir_model_data", "ir_model_fields", "ir_model_fields_selection",
    "ir_model_constraint", "ir_model_relation", "ir_model_access", "ir_ui_view",
    "ir_ui_view_group_rel", "ir_ui_menu", "ir_ui_menu_group_rel", "ir_translation", "ir_rule",
    "rule_group_rel", "ir_module_module", "ir_module_module_dependency",
    "ir_module_module_exclusion", "ir_module_category",
)
UNINSTALL_KINDS = ("data lost", "recomputed", "module data", "wizard", "metadata", "empty", "grew")


def owned_rows_sql(modules: list[str]) -> str:
    """Rows each model has through ``ir_model_data`` for these modules."""
    names = [m for m in modules if MODULE_NAME_RE.fullmatch(m)]
    if not names:
        raise IntakeError(["no module name to count rows for"])
    listed = ", ".join(f"'{m}'" for m in sorted(names))
    return (f"SELECT model, count(*) FROM ir_model_data WHERE module IN ({listed}) "
            "GROUP BY 1 ORDER BY 1")


def dependents_sql(modules: list[str]) -> str:
    """Every installed module that depends on these, directly or not: an uninstall
    takes them along. The first real intake reasoned from what each module owned,
    missed one, and would have dropped a field the client filled in."""
    names = [m for m in modules if MODULE_NAME_RE.fullmatch(m)]
    if not names:
        raise IntakeError(["no module name to find dependents of"])
    listed = ", ".join(f"'{m}'" for m in sorted(names))
    return (
        "WITH RECURSIVE dep(name) AS ("
        f"SELECT unnest(ARRAY[{listed}]::varchar[]) UNION "
        "SELECT m.name FROM ir_module_module m JOIN ir_module_module_dependency d "
        "ON d.module_id = m.id JOIN dep ON d.name = dep.name "
        "WHERE m.state IN ('installed', 'to upgrade')) "
        f"SELECT name FROM dep WHERE name NOT IN ({listed}) ORDER BY 1"
    )


def column_values_sql(columns: list[tuple[str, str]]) -> str:
    """How many rows hold a value, per ``(table, column)``: read where it still exists.

    Odoo stores an unset boolean as ``false`` and may store an unset char as
    ``''``: neither is a value anyone entered, and counting them reported every
    stock move as lost for a flag that was never set."""
    if not columns:
        raise IntakeError(["no column to count values for"])
    return " UNION ALL ".join(
        f"SELECT '{t}', '{c}', count(*) FILTER (WHERE {_ident(c)} IS NOT NULL AND "
        f"{_ident(c)}::text NOT IN ('false', ''))::text FROM public.{_ident(t)}"
        for t, c in columns if _NAME_RE.fullmatch(t) and re.fullmatch(r"[a-z0-9_]+", c))


def model_table(model: str) -> str:
    """The table Odoo gives a model by default; a custom ``_table`` is never excused."""
    return model.replace(".", "_")


def parse_counts(rows: list[list[str]]) -> dict[str, int]:
    out = {}
    for row in rows:
        if len(row) >= 2 and row[1].strip().isdigit():
            out[row[0]] = int(row[1])
    return out


def parse_columns(rows: list[list[str]]) -> set[tuple[str, str]]:
    return {(row[0], row[1]) for row in rows if len(row) >= 2}


@dataclass(frozen=True)
class UninstallChange:
    table: str
    column: str  # "" for the table's rows
    kind: str
    before: int
    after: int
    owned: int = 0


def _is_metadata(table: str) -> bool:
    """The registry's tables, and this tool's own record (``odwg_*``), which the
    rehearsal's re-neutralisation writes to."""
    return table in UNINSTALL_METADATA or table.startswith(("ir_act", "ir_ui_", "odwg_"))


def _is_wizard(table: str, transient_tables: set[str]) -> bool:
    """A transient model's table, or one of its many2many tables, which Odoo names
    after it (``<table>_<other>_rel``)."""
    return table in transient_tables or (
        table.endswith("_rel") and any(table.startswith(t + "_") for t in transient_tables))


def diff_uninstall(before_rows: dict[str, int], after_rows: dict[str, int],
                   before_cols: set[tuple[str, str]], after_cols: set[tuple[str, str]],
                   owned: dict[str, int], transient: set[str],
                   related: set[tuple[str, str]],
                   column_values: dict[tuple[str, str], int]) -> list[UninstallChange]:
    """Every difference an uninstall made, named.

    ``owned`` is rows per model the uninstalled modules had in ``ir_model_data``,
    ``transient`` and ``related`` are models and ``(model, field)`` pairs, all read
    from the database before; ``column_values`` counts, in that database, the
    rows holding a value in each column that is gone."""
    owned_t = {model_table(m): n for m, n in owned.items()}
    transient_t = {model_table(m) for m in transient}
    related_t = {(model_table(m), f) for m, f in related}
    changes = []
    for table, before in sorted(before_rows.items()):
        after = after_rows.get(table, 0)
        if after == before and table in after_rows:
            continue
        if _is_metadata(table):
            kind = "metadata"
        elif after > before:
            kind = "grew"
        elif _is_wizard(table, transient_t):
            kind = "wizard"
        elif before - after <= owned_t.get(table, 0):
            kind = "empty" if before == 0 else "module data"
        else:
            kind = "data lost"
        changes.append(UninstallChange(table, "", kind, before, after, owned_t.get(table, 0)))
    for table, column in sorted(before_cols - after_cols):
        if table not in after_rows:
            continue  # the table went, and its rows say what went with it
        values = column_values.get((table, column), 0)
        if (table, column) in related_t:
            kind = "recomputed"
        elif values == 0:
            kind = "empty"
        elif _is_wizard(table, transient_t) or _is_metadata(table):
            kind = "wizard" if _is_wizard(table, transient_t) else "metadata"
        else:
            kind = "data lost"
        changes.append(UninstallChange(table, column, kind, values, 0))
    return changes


def taken_along(asked: list[str], installed_before: set[str],
                installed_after: set[str]) -> list[str]:
    """Modules the uninstall removed beyond the ones asked for: their dependents."""
    return sorted((installed_before - installed_after) - set(asked))
