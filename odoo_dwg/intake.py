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
    column, so ``SELECT *`` on it fails rather than leaking."""
    if not (_NAME_RE.fullmatch(role) and _NAME_RE.fullmatch(database)):
        raise IntakeError([f"not a role or database name: {role!r}, {database!r}"])
    r = _ident(role)
    lines = [
        f"REVOKE TEMPORARY ON DATABASE {_ident(database)} FROM PUBLIC;",
        f"GRANT CONNECT ON DATABASE {_ident(database)} TO {r};",
        f"GRANT USAGE ON SCHEMA public TO {r};",
        f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {r};",
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
