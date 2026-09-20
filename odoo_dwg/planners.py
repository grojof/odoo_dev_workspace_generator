"""Pure command builders — the *plan* half of plan → preview → apply.

Every function returns a ``list[Command]`` and performs no I/O and no execution;
``system.apply_commands`` is the only thing that runs them. Existence checks are
injected (``exists`` predicate) so planners stay pure and testable while still
being able to *omit* work that is already present (e.g. a clone already in the
shared cache). The default predicate assumes nothing exists.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable
from pathlib import Path

from . import egress, templates, tester
from .i18n import tf
from .models import (
    MODULE_NAME_RE,
    PKG_RESOURCES_LAST_MAJOR,
    SETUPTOOLS_PIN,
    UV_PYTHON,
    Command,
    InterpreterChoice,
    MigrationEnv,
    PromotedModules,
    WorkspaceConfig,
    interpreter_from_pyvenv,
    odoo_major,
    setuptools_requirement,
)

Exists = Callable[[Path], bool]
# Current text of a file, or None when it is absent (injected, like Exists).
Read = Callable[[Path], str | None]
#: A file's current permission bits, or None when it is absent.
Mode = Callable[[Path], int | None]


def _never(_path: Path) -> bool:
    return False


def _unread(_path: Path) -> str | None:
    """Default reader: nothing exists yet, so everything is written (create path)."""
    return None


def heredoc_delimiter(content: str, base: str = "EOF") -> str:
    """A heredoc delimiter that no line of ``content`` equals.

    A quoted heredoc copies its body literally — no expansion — so the only way
    for content to reach the shell is a line equal to the delimiter, which ends
    the heredoc early and runs whatever follows. Profile values (a host, a prefix,
    an OCA repo name) end up in generated files, so the delimiter must be chosen
    against the content rather than assumed absent."""
    lines = set(content.splitlines())
    delimiter = base
    while delimiter in lines:
        delimiter += "_"
    return delimiter


def write_text_file_command(path: Path | str, content: str, mode: str = "644") -> list[Command]:
    """Emit a file via a quoted heredoc, then set its mode — as one command.

    One command, not two: a plan interrupted between them left a script written
    but not executable, and a refresh compares content only, so it reported the
    workspace up to date and never repaired the mode."""
    target = str(path)
    end = heredoc_delimiter(content)
    # The heredoc body ends with a newline of its own, so content that already
    # ends in one must not get a second: the file then holds exactly ``content``.
    body = content if content.endswith("\n") else f"{content}\n"
    # Written beside the target and renamed, never truncated in place: `cat >`
    # rewrites the same inode, and bash reads a running script by byte offset, so
    # regenerating `run_migration.sh` while it runs resumed it mid-token
    # ("oint: command not found"). A rename is atomic, so a running process keeps
    # the file it started with, and no reader ever sees a half-written one.
    temp = f"{target}.odwg-tmp"
    return [
        Command(
            tf("Write {} (mode {})", target, mode),
            f"cat > {shlex.quote(temp)} <<'{end}'\n{body}{end}\n"
            f"chmod {mode} {shlex.quote(temp)} && mv -f {shlex.quote(temp)} {shlex.quote(target)}",
        ),
    ]


def _clone_command(url: str, version: str, dest: Path) -> str:
    """Clone into a sibling and rename, so the final path exists only when the
    clone finished.

    A clone is skipped on the directory being there, and git leaves a partial
    working tree behind when it is interrupted after fetching objects — so an
    interrupted clone poisoned the shared cache permanently: nothing re-cloned it,
    the migration driver's advice ("regenerate the environment") was a no-op, and
    the workspace side failed later at `pip install -r` on a requirements.txt that
    was not there."""
    staging = f"{dest}.partial"
    return (
        f"rm -rf {shlex.quote(staging)} && "
        f"git clone --depth 1 --branch {shlex.quote(version)} --single-branch "
        f"{shlex.quote(url)} {shlex.quote(staging)} && "
        f"mv -T {shlex.quote(staging)} {shlex.quote(str(dest))}"
    )


def plan_repo_cache(cfg: WorkspaceConfig, exists: Exists = _never) -> list[Command]:
    """Clone each Odoo version and each OCA repo into the shared cache, once.

    A clone already present (``exists`` true) is skipped, never re-cloned or
    mutated, whether it is shallow or full. Clones are shallow
    (``--depth 1 --branch <version> --single-branch``): a development workspace
    never reads the branch history, which is most of a clone's size (an Odoo
    branch is ~5 GB with history, ~1 GB without). ``git fetch --unshallow``
    restores it for whoever needs ``log``/``blame``, and refreshing with
    ``pull --ff-only`` works the same on a shallow clone.
    """
    commands: list[Command] = []
    for version in cfg.versions:
        dest = cfg.odoo_clone_dir(version)
        if exists(dest):
            continue
        commands.append(
            Command(
                tf("Clone Odoo {} into the shared cache", version),
                _clone_command(cfg.odoo_repo_url, version, dest),
            )
        )
    for repo in cfg.oca_repos:
        for version in cfg.versions:
            dest = cfg.oca_clone_dir(repo, version)
            if exists(dest):
                continue
            url = f"{cfg.oca_url_base}/{repo}.git"
            commands.append(
                Command(
                    tf("Clone OCA {} ({}) into the shared cache", repo, version),
                    _clone_command(url, version, dest),
                )
            )
    return commands


def plan_workspace_tree(
    cfg: WorkspaceConfig,
    interpreters: dict[str, InterpreterChoice] | None = None,
) -> list[Command]:
    """Create the per-client workspace tree and write every generated file.

    Pure and create-friendly: directory creation is idempotent (``mkdir -p``) and
    the OCA symlinks use ``ln -sfn``; the create-only guard (refusing to clobber an
    existing workspace) lives in the workflow, not here.

    ``interpreters`` is passed through to the generated ``setup_venv.sh`` so the
    script rebuilds each venv with the interpreter the plan chose.
    """
    commands = plan_workspace_links(cfg)
    for path, content, mode in generated_files(cfg, interpreters):
        commands += write_text_file_command(path, content, mode)
    return commands


def plan_workspace_links(cfg: WorkspaceConfig) -> list[Command]:
    """The workspace directories and the per-version OCA symlinks. Idempotent
    (``mkdir -p``, ``ln -sfn``), so it is safe on an existing workspace."""
    commands: list[Command] = [
        Command(
            tf("Create workspace directories for {}", cfg.name),
            "mkdir -p "
            + " ".join(
                shlex.quote(str(p))
                for p in (
                    cfg.addons_custom_dir,
                    cfg.addons_oca_dir,
                    cfg.config_dir,
                    cfg.scripts_dir,
                    cfg.vscode_dir,
                )
            ),
        )
    ]

    # OCA symlinks, per version, into the shared cache.
    for repo in cfg.oca_repos:
        for version in cfg.versions:
            link = cfg.oca_symlink_dir(repo, version)
            target = cfg.oca_clone_dir(repo, version)
            commands.append(
                Command(
                    tf("Link OCA {} for Odoo {}", repo, version),
                    f"mkdir -p {shlex.quote(str(link.parent))} && "
                    # -T: replace the link itself. Without it, an existing real
                    # directory at that path would get the symlink nested inside.
                    f"ln -sfnT {shlex.quote(str(target))} {shlex.quote(str(link))}",
                )
            )
    return commands


def generated_files(
    cfg: WorkspaceConfig,
    interpreters: dict[str, InterpreterChoice] | None = None,
) -> list[tuple[Path, str, str]]:
    """Every file the tool generates in a workspace, as ``(path, content, mode)``.

    One list for creating a workspace and for refreshing an existing one, so the
    two can never disagree about what a workspace contains."""
    # The profile marker goes first, not last: it is what makes a directory a
    # *manageable* workspace. Written last, an interrupted generation left a tree
    # that create refused to touch ("already exists") and manage refused to load
    # ("no workspace.json") — a name the operator could only free with rm -rf.
    # Written first, any interruption from here on is repaired by Manage →
    # Refresh generated files, which writes every file that is missing.
    files: list[tuple[Path, str, str]] = [(cfg.profile_file, cfg.to_json(), "644")]
    # Per-version odoo.conf and run scripts.
    for version in cfg.versions:
        major = odoo_major(version)
        files.append((cfg.config_file(version), templates.render_odoo_conf(cfg, version), "644"))
        files.append(
            (cfg.scripts_dir / f"run-odoo{major}.sh", templates.render_run_sh(cfg, version), "755")
        )
    # Workspace-wide scripts and editor files.
    files += [
        (cfg.scripts_dir / "setup_venv.sh", templates.render_setup_venv_sh(cfg, interpreters), "755"),
        (cfg.vscode_dir / "settings.json", templates.render_vscode_settings(cfg), "644"),
        (cfg.vscode_dir / "extensions.json", templates.render_vscode_extensions(), "644"),
        (cfg.vscode_dir / "tasks.json", templates.render_vscode_tasks(cfg), "644"),
        (cfg.vscode_dir / "launch.json", templates.render_vscode_launch(cfg), "644"),
        (cfg.code_workspace_file, templates.render_code_workspace(cfg), "644"),
    ]
    # Only when the language server can open at least one version (it refuses < 14).
    if templates.odools_versions(cfg):
        files.append((cfg.odools_file, templates.render_odools_toml(cfg), "644"))
    files.append((cfg.readme_file, templates.render_workspace_readme(cfg, interpreters), "644"))
    return files



def plan_refresh_files(
    cfg: WorkspaceConfig,
    interpreters: dict[str, InterpreterChoice] | None,
    read: Read,
    stamp: str = "",
    mode_of: Mode | None = None,
) -> list[Command]:
    """Bring an existing workspace's generated files up to date with the tool.

    Only files whose content would change are written. A file that exists and
    changes is first copied to ``<file>.bak-<stamp>``, since it may carry hand edits (a
    tuned ``odoo.conf``, an extra launch configuration). ``read`` returns a file's
    current text, or None when it is absent; the workflow passes a real reader.
    Nothing outside the generated files is touched: addons, venvs, clones and
    databases are left as they are."""
    commands: list[Command] = []
    for path, content, mode in generated_files(cfg, interpreters):
        current = read(path)
        # Files written before the heredoc stopped adding a trailing blank line
        # differ only in that; they are current, not worth a backup.
        if current is not None and current.rstrip("\n") == content.rstrip("\n"):
            # The content is current; the mode may not be. A restore from an
            # archive without `-p`, or a `chmod -R`, leaves a generated script
            # unable to run, and comparing text alone reported the workspace up
            # to date. Only the owner's execute bit is repaired, and only on a
            # file meant to be executable: rewriting the whole mode would undo an
            # operator who narrowed `odoo.conf`, which carries `admin_passwd`.
            actual = mode_of(path) if mode_of else None
            if int(mode, 8) & 0o100 and actual is not None and not actual & 0o100:
                commands.append(
                    Command(
                        tf("Make {} executable again", str(path)),
                        f"chmod u+x {shlex.quote(str(path))}",
                    )
                )
            continue
        if current is not None:
            # ``stamp`` (the workflow's clock) keeps every earlier backup.
            backup = Path(f"{path}.bak-{stamp}" if stamp else f"{path}.bak")
            commands.append(
                Command(
                    tf("Back up {} to {}", str(path), backup.name),
                    f"cp -p {shlex.quote(str(path))} {shlex.quote(str(backup))}",
                )
            )
        else:
            commands.append(
                Command(
                    tf("Create directory for {}", str(path)),
                    f"mkdir -p {shlex.quote(str(path.parent))}",
                )
            )
        commands += write_text_file_command(path, content, mode)
    return commands


# --- provisioning (F2) -----------------------------------------------------

# Odoo build/system dependencies (Debian/Ubuntu apt). This is the set validated
# end-to-end during F1 acceptance on Ubuntu 24.04.
# apt runs unattended: a debconf or conffile dialog would hang a plan with its
# prompt hidden, since a step's output is captured unless --verbose is on.
_APT = "DEBIAN_FRONTEND=noninteractive apt-get -y -o Dpkg::Options::=--force-confold"
APT_INSTALL = f"{_APT} install"
APT_PURGE = f"{_APT} purge"

BUILD_DEPS: tuple[str, ...] = (
    "build-essential", "pkg-config", "python3-dev", "python3-venv", "python3-pip", "git",
    "libpq-dev", "libldap2-dev", "libsasl2-dev", "libssl-dev", "libffi-dev",
    "libxml2-dev", "libxslt1-dev", "libjpeg-dev", "zlib1g-dev", "libtiff-dev",
    "libopenjp2-7-dev", "liblcms2-dev", "libwebp-dev", "libharfbuzz-dev",
    "libfribidi-dev", "fontconfig", "postgresql-client",
)

# Pinned patched wkhtmltopdf 0.12.6.1-3 assets (amd64) with SHA-256, ported from
# the sibling app (verified against Odoo's own Dockerfile checksum). Codenames
# without a compatible asset resolve to None so the caller recommends the distro
# package or skip — never a guessed URL.
_WKHTMLTOPDF_BASE_URL = "https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3"
_WKHTMLTOPDF_ASSETS: dict[str, tuple[str, str]] = {
    # Upstream ships no noble build; the jammy one is what installs on 24.04.
    "noble": ("wkhtmltox_0.12.6.1-3.jammy_amd64.deb",
              "4f723b2691ad8638a9df960e0421d346d7315083e3583a334f33362280ddba15"),
}


def wkhtmltopdf_target_version(major: int) -> str:
    """Odoo-recommended wkhtmltopdf: 0.12.5 for Odoo <= 14, 0.12.6 for >= 15."""
    return "0.12.5" if major <= 14 else "0.12.6"


def resolve_wkhtmltopdf_asset(codename: str) -> tuple[str, str, str] | None:
    """``(url, filename, sha256)`` for the patched 0.12.6 build matching ``codename``,
    or None when no verified asset is pinned (caller recommends distro/skip)."""
    entry = _WKHTMLTOPDF_ASSETS.get((codename or "").strip().lower())
    if not entry:
        return None
    filename, sha256 = entry
    return f"{_WKHTMLTOPDF_BASE_URL}/{filename}", filename, sha256


def plan_build_deps() -> list[Command]:
    """Idempotent apt install of the Odoo build/system dependencies."""
    packages = " ".join(BUILD_DEPS)
    return [
        Command(tf("Update apt package lists"), "apt-get update"),
        Command(tf("Install Odoo build dependencies"), f"{APT_INSTALL} {packages}"),
    ]


def plan_postgresql(role: str) -> list[Command]:
    """Install PostgreSQL, enable/start it, create an idempotent LOGIN CREATEDB dev
    role, and set loopback (127.0.0.1/::1) to trust for local development."""
    role_sql = (
        "DO $$ BEGIN "
        f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{role}') THEN "
        f"CREATE ROLE {role} WITH LOGIN CREATEDB; "
        "END IF; END $$;"
    )
    return [
        Command(tf("Install PostgreSQL"), f"apt-get update && {APT_INSTALL} postgresql"),
        Command(tf("Enable and start PostgreSQL"), "systemctl enable --now postgresql"),
        Command(
            tf("Create development role {} (if missing)", role),
            f"sudo -u postgres psql -X -v ON_ERROR_STOP=1 -c {shlex.quote(role_sql)}",
        ),
    ] + plan_pg_hba_trust(role)


# A TCP rule for *every* role whose method is `trust`, whatever address it names.
# Enumerating addresses was wrong twice over (`localhost`, then `all`/`0.0.0.0/0`):
# an address can contain loopback without naming it, so the method is what this
# tool reasons about. The address is one token, or an address and a netmask.
# A TCP rule whose *role* field is the keyword `all` and whose method is `trust`,
# on any database: the database bounds which database is exposed, never whether
# one is. The role field is matched unquoted on purpose — `"all"` is a role named
# `all`, which PostgreSQL does not match a connection against.
#: The role field as PostgreSQL reads it: a comma list, where an unquoted `all`
#: anywhere means every role. `host all all,bob … trust` is a live blanket trust.
_ROLE_LIST_WITH_ALL = "([^[:space:],]+,)*all(,[^[:space:],]+)*"
BLANKET_TRUST_RULE = (
    "^([[:space:]]*host[a-z]*[[:space:]]+[^[:space:]]+[[:space:]]+"
    f"{_ROLE_LIST_WITH_ALL}"
    "[[:space:]]+[^[:space:]]+"
    "([[:space:]]+[0-9a-fA-F.:]+)?[[:space:]]+)trust([[:space:]]|$)"
)
# Any host rule at all: the anchor the role's own line is inserted before, so it
# is never shadowed by one of them.
ANY_HOST_RULE = "^[[:space:]]*host[a-z]*[[:space:]]"


def plan_pg_hba_trust(role: str) -> list[Command]:
    """Give the development role a loopback trust line and take away any blanket
    one. Separate from ``plan_postgresql`` so a host that already has PostgreSQL
    and the role still gets its ``pg_hba.conf`` narrowed."""
    v4 = f"host    all             {role}             127.0.0.1/32            trust"
    v6 = f"host    all             {role}             ::1/128                 trust"
    # "Is the role's trust line *reached*", not "is it present": pg_hba is
    # first-match-wins, so a line below a rule for every role is never read, and
    # inserting nothing would leave the role unable to connect. Mirrors
    # ``system.pg_hba_loopback_state``. Interval expressions are avoided so this
    # behaves the same under mawk (Ubuntu's awk) and gawk.
    reached = (
        "awk '"
        "/^[[:space:]]*#/ { next } "
        "$1 !~ /^host/ { next } "
        "NF < 5 { next } "
        "{ "
        # `type database user address [netmask] method`: the netmask is there only
        # when the address carries no prefix length. Same reading as pghba.Rule.
        'm = 5; if ($4 !~ /\\// && NF > 5 && $5 ~ /^[0-9a-fA-F.:]+$/) m = 6; '
        # Both fields are comma lists, and PostgreSQL matches the keyword `all`
        # anywhere in one. Quoting a plain name changes nothing, but `"all"` is a
        # role *named* all and not the keyword, so that test comes before the
        # quotes are stripped.
        'every = 0; mine = 0; every_db = 0; '
        'n = split($3, part, ","); '
        'for (k = 1; k <= n; k++) { e = part[k]; if (e == "all") every = 1; '
        f'gsub(/^"|"$/, "", e); if (e == "{role}") mine = 1 }} '
        'n = split($2, part, ","); '
        'for (k = 1; k <= n; k++) if (part[k] == "all") every_db = 1; '
        "if (!every && !mine) next; "
        # The first rule matching this connection is the only one PostgreSQL
        # reads, so the answer is given here — whatever that rule turns out to be.
        # Plain `host` only, like the probe and the verification step: with TLS on
        # a `hostnossl` rule is never consulted, and counting one as the role's
        # trust line would insert nothing and then fail the step it cannot fix.
        'found = ($1 == "host" && mine && every_db && $(m) == "trust"); '
        "exit } "
        "END { exit !found }' \"$PGHBA\""
    )
    # Only the development role, not every role: a blanket loopback trust would let
    # any local user connect as the postgres superuser. Any earlier blanket trust
    # this tool wrote is put back to scram-sha-256. The insertion tries the usual
    # anchor first, then any host rule, then the end of the file — and the step
    # fails loudly rather than reporting success while the role still cannot
    # connect.
    script = "\n".join([
        'set -e',
        'PGHBA=$(sudo -u postgres psql -X -tAc "SHOW hba_file;")',
        '[ -f "$PGHBA" ] || { echo "pg_hba.conf not found: $PGHBA" >&2; exit 1; }',
        # Rules this step cannot see, line by line: a record continued with a
        # trailing backslash, or rules pulled in from another file. Narrowing
        # what it can see would leave the rest and report success.
        'grep -qE \'\\\\[[:space:]]*$\' "$PGHBA" && { echo "$PGHBA has line '
        'continuations (a record split with a trailing backslash); join them and '
        'run this again — this step reads one rule per line" >&2; exit 1; }',
        r'grep -qiE "^[[:space:]]*include(_if_exists|_dir)?[[:space:]]" "$PGHBA" && '
        r'{ echo "$PGHBA pulls in rules with an include directive; this step cannot '
        r'see them — narrow that file by hand, or inline its rules" >&2; exit 1; }',
        # A quoted database field may contain blanks, and every pattern below
        # counts fields by whitespace. The check reads such a rule correctly
        # through the server, so refusing here is the difference between saying
        # so and silently skipping the one rule that matters.
        'grep -qE \'^[[:space:]]*host[a-z]*[[:space:]]+"\' "$PGHBA" && '
        '{ echo "$PGHBA has a rule whose database field is quoted; this step reads '
        'fields by whitespace and cannot rewrite it — narrow that rule by hand" >&2; '
        'exit 1; }',
        # A list continued after a blank (`odoo, all`) is one list to the server
        # and two fields to every pattern below.
        'grep -qE \'^[[:space:]]*host[a-z]*[[:space:]]+[^#]*,[[:space:]]\' "$PGHBA" && '
        '{ echo "$PGHBA has a rule whose list continues after a blank (as in \\`odoo, all\\`); '
        'this step reads fields by whitespace and cannot rewrite it — join the list, or '
        'narrow the rule by hand" >&2; exit 1; }',
        # `@file` names its databases or roles from another file, which the server
        # expands and this step cannot see. Leaving such a rule while reporting
        # success is how a blanket trust survived a narrowing that said it worked.
        'grep -qE \'^[[:space:]]*host[a-z]*[[:space:]]+([^#]*[[:space:],])?@\' "$PGHBA" && '
        '{ echo "$PGHBA has a rule naming its databases or roles from a file (@…); '
        'this step cannot read what that file holds — inline those names, or narrow '
        'the rule by hand" >&2; exit 1; }',
        # \1 is everything up to the method, \5 the whitespace or end of line
        # after it — keep both in step with BLANKET_TRUST_RULE's groups, which
        # the role list adds two of.
        f'sed -ri "s#{BLANKET_TRUST_RULE}#\\1scram-sha-256\\5#" "$PGHBA"',
        f"if ! {reached}; then",
        # The insertion must be at least as permissive as the downgrade above, or
        # the role's line lands *after* a rule that matches the same connection
        # first — pg_hba is first-match-wins, and the line would never be read.
        # Before the *first* host rule of any kind: anything later could be a rule
        # that already matches this connection (a group role, a wider address).
        f'  if grep -qE {shlex.quote(ANY_HOST_RULE)} "$PGHBA"; then',
        f'    sed -ri "0,/{ANY_HOST_RULE}/s##{v4}\\n{v6}\\n&#" "$PGHBA"',
        '  else',
        # Leading newline: a file with no final one would otherwise have its last
        # record fused with the first inserted line, which pg_hba cannot parse.
        f'    printf "\\n%s\\n%s\\n" {shlex.quote(v4)} {shlex.quote(v6)} >> "$PGHBA"',
        '  fi',
        'fi',
        f'{reached} || '
        f'{{ echo "the loopback trust line for {role} in $PGHBA is missing or is shadowed by an '
        f'earlier rule" >&2; exit 1; }}',
    ])
    # The grep proves the line exists, not that it is reached: an earlier rule
    # matching the same connection wins, and pg_hba is first-match-wins. Only a
    # connection proves the narrowing did what it says.
    connect = (
        f"psql -X -w -h 127.0.0.1 -U {shlex.quote(role)} -d postgres -tAc 'SELECT 1' >/dev/null 2>&1"
    )
    probe = "\n".join([
        # The retry is on the connection itself — the reload is asynchronous, and
        # retrying anything else proves nothing about it.
        "tries=0",
        'while [ "$tries" -lt 5 ]; do',
        f"  {connect} && ok=1 && break",
        "  tries=$((tries + 1)); sleep 1",
        "done",
        f'[ "${{ok:-}}" = 1 ] || {{ echo "{role} cannot connect over loopback after the reload — '
        f"check that PostgreSQL is running, and the rules above the ones this step added in "
        f'$(sudo -u postgres psql -X -tAc \"SHOW hba_file;\")" >&2; exit 1; }}',
    ])
    return [
        Command(
            tf("Trust loopback connections of {} for local development (pg_hba)", role),
            script,
        ),
        Command(tf("Reload PostgreSQL"), "systemctl reload postgresql"),
        Command(tf("Ask PostgreSQL to read back the rules for {}", role), _pg_hba_audit(role)),
        Command(tf("Check that {} connects over loopback", role), probe),
    ]


def _pg_hba_audit(role: str) -> str:
    """Have the server parse what was just written, instead of trusting the text.

    `pg_hba_file_rules` folds continuations, expands `include*` and names the file
    each rule came from, so this sees rules the rewriter above cannot — a check
    written against a different source of truth.

    It reads the *file*, re-parsed at query time, not the rule set the postmaster
    has loaded: PostgreSQL exposes no view of that. The `error` check is what ties
    the two together — a file the server cannot parse is one it refused to load,
    so the rules in force are still the previous ones — and the connection check
    that follows is what proves the loaded set actually lets the role in."""
    # `file_name` and `rule_number` exist from PostgreSQL 15; `include` directives
    # (the only reason a rule can come from another file) from 16. Below 15 the
    # configured file is the only one there is, so `hba_file` names it.
    tcp_trust = "type LIKE 'host%' AND auth_method = 'trust'"
    ask = "sudo -u postgres psql -X -w -tAc"
    return "\n".join([
        "set -e",
        f"PGVER=$({ask} 'SHOW server_version_num')",
        'if [ "${PGVER:-0}" -ge 150000 ]; then',
        "  LOC=\"coalesce(file_name, '') || ':' || line_number\"; ORD=rule_number",
        "else",
        "  LOC=\"(SELECT setting FROM pg_settings WHERE name='hba_file') || ':' || line_number\"",
        "  ORD=line_number",
        "fi",
        # Does the rule at `file:line` name every role, or a role *named* `all`?
        # A file this cannot open leaves the view's answer standing: treating an
        # unreadable line as narrow is the one mistake with a cost.
        # Called only for a rule the *server* says trusts every role. The line is
        # read for one bit the view lost — whether `all` was written "all" — and
        # may say nothing else: it answers "not every role" only when it is a
        # shape this reads exactly as `hba.c` does (plain or blank-free quoted
        # names, no `@file`, no continuation, no `#` before the method) and that
        # reading holds no bare `all`. Anything else keeps the server's answer.
        # Four fixes each let this narrow the server's answer in one more shape,
        # and each was a blanket trust reported as narrowed.
        "names_every_role() {",
        '  hba_file=${1%:*}; hba_line=${1##*:}',
        '  [ -f "$hba_file" ] || return 0',
        '  hba_text=$(sed -n "${hba_line}p" "$hba_file")',
        '  printf "%s\\n" "$hba_text" | grep -qE "$EXACT" || return 0',
        # 0 = "every role": a bare `all` among elements this read exactly.
        '  printf "%s\\n" "$hba_text" | grep -qE "$ROLEALL"',
        "}",
        # A file the server cannot parse is a file it did not load: `pg_ctl reload`
        # returns 0 whatever happens, so without this the steps below would read a
        # narrowed file while the rules in force are still the old ones.
        f'BAD=$({ask} "SELECT $LOC FROM pg_hba_file_rules WHERE error IS NOT NULL '
        'ORDER BY line_number LIMIT 1")',
        '[ -z "$BAD" ] || { echo "PostgreSQL cannot parse the rule at $BAD, so it refused to load '
        'the file — the rules it is running are still the previous ones" >&2; exit 1; }',
        # Roles named by pattern or group: the view reports the field verbatim and
        # this step cannot tell whether it covers every role, so it says so.
        f'WIDE=$({ask} "SELECT $LOC FROM pg_hba_file_rules WHERE {tcp_trust} '
        "AND EXISTS (SELECT 1 FROM unnest(user_name) u WHERE u LIKE '/%' OR u LIKE '+%') "
        f'ORDER BY $ORD LIMIT 1")',
        '[ -z "$WIDE" ] || { echo "the trust rule at $WIDE names its roles by pattern or group, '
        'which this step cannot rule out — narrow it by hand" >&2; exit 1; }',
        # `"all"` in the file is a role *named* all, which PostgreSQL does not
        # match a connection against, though the view reports it exactly like the
        # keyword. Only the line tells them apart — and only in that field: the
        # server reads `host all all "127.0.0.1/32" trust` as the blanket trust it
        # is. Both walks below ask the same question of the same field.
        # A field this reads exactly as the server does: elements that are plain
        # words or quoted names with no blank, `#`, `@` or backslash inside, joined
        # by commas with no blank around them. Then, a bare `all` among them.
        "ELEM='(\"[^\"[:space:]#@\\\\]*\"|[^\"[:space:]#@\\\\,]+)'",
        "EXACT=\"^[[:space:]]*host[a-z]*[[:space:]]+$ELEM(,$ELEM)*[[:space:]]+$ELEM(,$ELEM)*"
        "[[:space:]]+[^[:space:]#]+([[:space:]]+[0-9a-fA-F.:]+)?[[:space:]]+[a-z0-9-]+"
        "[[:space:]]*(#.*)?\\$\"",
        "ROLEALL=\"^[[:space:]]*host[a-z]*[[:space:]]+$ELEM(,$ELEM)*"
        "[[:space:]]+($ELEM,)*all(,$ELEM)*[[:space:]]\"",
        # -f: a glob character in a path must not be expanded while splitting, and
        # a location is `file:line`, so splitting is on newlines only.
        "set -f",
        'IFS="',
        '"',
        f'LEFT=$({ask} "SELECT $LOC FROM pg_hba_file_rules WHERE {tcp_trust} '
        f'AND \'all\' = ANY(user_name) ORDER BY $ORD")',
        "for loc in $LEFT; do",
        '  [ -n "$loc" ] || continue',
        '  names_every_role "$loc" || continue',
        '  echo "a rule still trusts every role over TCP, at $loc — this step did not narrow it '
        '(it may live in a file it cannot rewrite)" >&2',
        "  exit 1",
        "done",
        # The rule PostgreSQL matches for the role: the first one covering it, by
        # field — the same reading the rewriter's awk and `provision check` use, so
        # none of the three can pass a file the others fail. Only a plain `host`
        # rule reaches the role (with TLS on, `hostnossl` is never consulted), which
        # is why the verdict is narrower than the rules walked.
        f'ROWS=$({ask} "SELECT $LOC || \'|\' || '
        f"CASE WHEN type = 'host' AND auth_method = 'trust' AND '{role}' = ANY(user_name) "
        "AND 'all' = ANY(database) THEN 'ok' ELSE 'no' END || '|' || "
        f"CASE WHEN '{role}' = ANY(user_name) THEN 'named' ELSE 'keyword' END "
        f"FROM pg_hba_file_rules WHERE type LIKE 'host%' "
        f"AND ('{role}' = ANY(user_name) OR 'all' = ANY(user_name)) "
        f'ORDER BY $ORD")',
        'FIRST=; WHERE=none',
        "for row in $ROWS; do",
        '  [ -n "$row" ] || continue',
        '  loc=${row%%|*}; rest=${row#*|}; verdict=${rest%%|*}; how=${rest##*|}',
        # Matched only through `all`: it covers the role only if that field really
        # is the keyword.
        '  if [ "$how" = keyword ]; then names_every_role "$loc" || continue; fi',
        '  FIRST=$verdict; WHERE=$loc; break',
        "done",
        "set +f",
        "unset IFS",
        f'[ "$FIRST" = ok ] || {{ echo "the first rule PostgreSQL matches for {role} is at $WHERE, '
        f'not the trust rule this step added" >&2; exit 1; }}',
    ])


def plan_wkhtmltopdf(major: int, codename: str) -> list[Command]:
    """Install the Odoo-recommended patched wkhtmltopdf for the host codename,
    verifying its SHA-256 (abort on mismatch). Returns no commands when no verified
    asset is pinned (0.12.5/<=14 or an unmapped codename) — caller recommends distro."""
    if wkhtmltopdf_target_version(major) != "0.12.6":
        return []
    asset = resolve_wkhtmltopdf_asset(codename)
    if asset is None:
        return []
    url, filename, sha256 = asset
    tmp = f"{_ROOT_WORK_DIR}/{filename}"
    return [
        Command(tf("Ensure curl is available"),
                f"command -v curl >/dev/null 2>&1 || (apt-get update && {APT_INSTALL} curl)"),
        Command(tf("Create download directory {}", _ROOT_WORK_DIR),
                f"mkdir -m 700 -p {shlex.quote(_ROOT_WORK_DIR)}"),
        Command(tf("Download patched wkhtmltopdf ({})", filename),
                f"curl -fSL -o {shlex.quote(tmp)} {shlex.quote(url)}"),
        Command(tf("Verify wkhtmltopdf SHA-256 (abort on mismatch)"),
                f"echo {shlex.quote(sha256 + '  ' + tmp)} | sha256sum -c -"),
        Command(tf("Install verified wkhtmltopdf .deb"),
                f"{APT_INSTALL} {shlex.quote(tmp)}"),
        # The patched build is the whole reason for this step: an unpatched
        # distribution one earlier on PATH would leave it reporting success with
        # Odoo's PDF reports still degraded.
        Command(
            tf("Check that the patched wkhtmltopdf is the one on PATH"),
            'wkhtmltopdf --version 2>/dev/null | grep -qi "with patched qt" || '
            '{ echo "the wkhtmltopdf on PATH is not the patched build: '
            '$(command -v wkhtmltopdf || echo none) — PDF reports will be degraded" >&2; exit 1; }',
        ),
        Command(tf("Remove downloaded wkhtmltopdf .deb"), f"rm -f {shlex.quote(tmp)}"),
    ]


def plan_node_rtlcss() -> list[Command]:
    """Optional rtlcss, which Odoo runs only to mirror its CSS for a right-to-left
    language (base/models/assetsbundle.py, run_rtlcss); without it Odoo logs a warning
    and serves the stylesheet unmirrored. Node.js is needed only to run it."""
    return [
        # Without recommends: they pulled in 455 packages on Ubuntu 24.04, a GUI
        # terminal among them, for what only needs node and npm.
        Command(tf("Install Node.js and npm"),
                f"apt-get update && {APT_INSTALL} --no-install-recommends nodejs npm"),
        Command(tf("Install rtlcss globally"), "npm install -g rtlcss"),
    ]


# --- egress control and mail capture (optional) ----------------------------

# Root downloads go here, never /tmp: a local user could pre-create a predictable
# /tmp path they own and swap a verified file before it is installed.
_ROOT_WORK_DIR = "/var/cache/odoo_dwg"
_POLICY_RC = "/usr/sbin/policy-rc.d"
_POLICY_MARK = "odoo_dwg: keep opensnitch stopped until it is configured"


def plan_opensnitch(resolvers: list[str], installed_version: str | None = None) -> list[Command]:
    """Install OpenSnitch from its pinned upstream packages, harden its config and
    write the owned baseline rules, then (re)start it.

    The packages are verified by SHA-512 and the service is kept from starting
    until the configuration and rules are in place (``policy-rc.d``): the shipped
    defaults would flush open connections and allow everything. When the pinned
    version is already installed, only the configuration, rules and restart run."""
    commands: list[Command] = []
    if not (installed_version or "").startswith(egress.OPENSNITCH_VERSION):
        workdir = f"{_ROOT_WORK_DIR}/opensnitch"
        debs = [f"{workdir}/{name}" for name, _sha in egress.OPENSNITCH_PACKAGES]
        commands += [
            Command(tf("Ensure curl is available"),
                    f"command -v curl >/dev/null 2>&1 || (apt-get update && {APT_INSTALL} curl)"),
            Command(tf("Create download directory {}", workdir),
                    f"rm -rf {shlex.quote(workdir)} && mkdir -m 700 -p {shlex.quote(workdir)}"),
        ]
        for (name, sha512), deb in zip(egress.OPENSNITCH_PACKAGES, debs, strict=True):
            commands += [
                Command(tf("Download {}", name),
                        f"curl -fSL -o {shlex.quote(deb)} "
                        f"{shlex.quote(egress.OPENSNITCH_BASE_URL + '/' + name)}"),
                Command(tf("Verify {} SHA-512 (abort on mismatch)", name),
                        f"echo {shlex.quote(sha512 + '  ' + deb)} | sha512sum -c -"),
            ]
        install = " ".join(shlex.quote(deb) for deb in debs)
        commands += [
            Command(
                tf("Install OpenSnitch {} without starting it", egress.OPENSNITCH_VERSION),
                # Never replace someone else's policy-rc.d (one left by an
                # interrupted earlier run carries our mark and is reused). Ours is
                # removed on every exit, including Ctrl-C and a failed install.
                f"if [ -e {_POLICY_RC} ] && ! grep -q '{_POLICY_MARK}' {_POLICY_RC}; then "
                f"echo '{_POLICY_RC} already exists and is not ours' >&2; exit 1; fi; "
                f"trap 'rm -f {_POLICY_RC}' EXIT INT TERM HUP; "
                f"printf '#!/bin/sh\\n# {_POLICY_MARK}\\nexit 101\\n' > {_POLICY_RC} && "
                f"chmod 755 {_POLICY_RC} && "
                f"{APT_INSTALL} {install}",
            ),
            Command(tf("Remove downloaded packages"), f"rm -rf {shlex.quote(workdir)}"),
        ]
    commands.append(
        Command(
            tf("Harden {}", egress.OPENSNITCH_CONFIG),
            f"python3 - <<'PYEOF'\n{egress.hardening_script()}PYEOF",
        )
    )
    commands.append(
        Command(
            tf("Replace the tool's own OpenSnitch rules ({}*)", egress.RULE_PREFIX),
            f"rm -f {shlex.quote(egress.OPENSNITCH_RULES_DIR)}/{egress.RULE_PREFIX}*.json",
        )
    )
    for rule in egress.baseline_rules(resolvers):
        path = f"{egress.OPENSNITCH_RULES_DIR}/{egress.rule_filename(rule)}"
        commands += write_text_file_command(path, egress.render_rule(rule), "644")
    commands.append(
        Command(tf("Enable and (re)start OpenSnitch"),
                "systemctl enable opensnitch && systemctl restart opensnitch")
    )
    return commands


def plan_mailpit(installed_version: str | None = None) -> list[Command]:
    """Install Mailpit from its pinned release (SHA-256 verified) as a system
    service bound to 127.0.0.1; only the unit and restart run when the pinned
    version is already installed."""
    commands: list[Command] = []
    if installed_version != egress.MAILPIT_VERSION:
        workdir = f"{_ROOT_WORK_DIR}/mailpit"
        archive = f"{workdir}/mailpit-linux-amd64.tar.gz"
        commands += [
            Command(tf("Ensure curl is available"),
                    f"command -v curl >/dev/null 2>&1 || (apt-get update && {APT_INSTALL} curl)"),
            Command(tf("Create download directory {}", workdir),
                    f"rm -rf {shlex.quote(workdir)} && mkdir -m 700 -p {shlex.quote(workdir)}"),
            Command(tf("Download Mailpit {}", egress.MAILPIT_VERSION),
                    f"curl -fSL -o {shlex.quote(archive)} {shlex.quote(egress.MAILPIT_URL)}"),
            Command(tf("Verify Mailpit SHA-256 (abort on mismatch)"),
                    f"echo {shlex.quote(egress.MAILPIT_SHA256 + '  ' + archive)} | sha256sum -c -"),
            Command(tf("Install Mailpit to {}", egress.MAILPIT_BINARY),
                    f"tar -xzf {shlex.quote(archive)} -C {shlex.quote(workdir)} mailpit && "
                    f"install -m 755 {shlex.quote(workdir + '/mailpit')} "
                    f"{shlex.quote(egress.MAILPIT_BINARY)}"),
            Command(tf("Remove downloaded files"), f"rm -rf {shlex.quote(workdir)}"),
        ]
    commands += write_text_file_command(egress.MAILPIT_UNIT, egress.render_mailpit_unit(), "644")
    commands.append(
        Command(tf("Enable and (re)start Mailpit"),
                "systemctl daemon-reload && systemctl enable mailpit && systemctl restart mailpit")
    )
    return commands


OPENSNITCH_PACKAGE_NAMES = ("opensnitch", "python3-opensnitch-ui")


def plan_service_switch(unit: str, on: bool) -> list[Command]:
    """Turn a service on or off, and keep it that way across restarts."""
    if on:
        return [Command(tf("Turn on {} (and at every start)", unit),
                        f"systemctl enable --now {shlex.quote(unit)}")]
    return [Command(tf("Turn off {} (and keep it off after a restart)", unit),
                    f"systemctl disable --now {shlex.quote(unit)}")]


def plan_opensnitch_uninstall() -> list[Command]:
    """Stop OpenSnitch, remove the tool's own rules, and purge the packages with the
    dependencies they pulled in. The operator's own rules are left in place."""
    packages = " ".join(OPENSNITCH_PACKAGE_NAMES)
    return [
        Command(tf("Turn off {} (and keep it off after a restart)", "opensnitch"),
                "systemctl disable --now opensnitch"),
        Command(tf("Remove the tool's own OpenSnitch rules ({}*)", egress.RULE_PREFIX),
                f"rm -f {shlex.quote(egress.OPENSNITCH_RULES_DIR)}/{egress.RULE_PREFIX}*.json"),
        Command(tf("Purge OpenSnitch and the packages it pulled in"),
                f"{APT_PURGE} --autoremove {packages}"),
        # The packet-queue modules it loaded stay in the kernel until reboot otherwise.
        Command(tf("Unload the kernel modules it used"),
                "modprobe -r nft_queue nfnetlink_queue 2>/dev/null || true"),
    ]


def plan_mailpit_uninstall() -> list[Command]:
    """Stop Mailpit and remove its unit, binary and captured mail."""
    return [
        Command(tf("Turn off {} (and keep it off after a restart)", "mailpit"),
                "systemctl disable --now mailpit"),
        Command(tf("Remove {}", egress.MAILPIT_UNIT),
                f"rm -f {shlex.quote(egress.MAILPIT_UNIT)} && systemctl daemon-reload"),
        Command(tf("Remove {}", egress.MAILPIT_BINARY), f"rm -f {shlex.quote(egress.MAILPIT_BINARY)}"),
        # DynamicUser keeps the state in /var/lib/private/, linked from /var/lib/.
        Command(tf("Remove the captured mail ({})", "/var/lib/mailpit"),
                "rm -rf /var/lib/mailpit /var/lib/private/mailpit"),
    ]


def _psql(database: str, host: str, port: int, user: str, sql: str) -> str:
    return (
        f"psql -X -w -h {shlex.quote(host)} -p {int(port)} -U {shlex.quote(user)} "
        f"-d {shlex.quote(database)} -v ON_ERROR_STOP=1 -c {shlex.quote(sql)}"
    )


def plan_mail_capture(database: str, host: str, port: int, user: str) -> list[Command]:
    """Stop a database's mail leaving, leaving its configuration where it is.

    Nothing the client configured is overwritten: its servers are deactivated and
    one pointing at Mailpit is added, so ``plan_mail_restore`` can give the
    database back exactly what it had."""
    return [
        Command(
            tf("Capture the mail of database {} in Mailpit", database),
            _psql(database, host, port, user, egress.mail_capture_sql()),
        )
    ]


def plan_mail_restore(database: str, host: str, port: int, user: str) -> list[Command]:
    """Give a captured database back the mail configuration it had. Fails, rather
    than reporting success, on a database that was never captured."""
    return [
        Command(
            tf("Restore the mail configuration of database {}", database),
            _psql(database, host, port, user, egress.mail_restore_sql()),
        )
    ]


def plan_migration_clones(env: MigrationEnv, exists: Exists = _never) -> list[Command]:
    """Clone what each step needs, shallow, skipping clones already present.

    Every step needs its OpenUpgrade checkout. From 14 it also needs the matching
    Odoo clone, because the checkout is only an add-on collection; up to 13 the
    checkout *is* a full Odoo fork, so cloning Odoo separately would fetch a
    gigabyte nothing reads."""
    commands: list[Command] = []
    for version in env.chain():
        ou_dest = env.openupgrade_clone_dir(version)
        if not exists(ou_dest):
            commands.append(
                Command(
                    tf("Clone OpenUpgrade {}", version),
                    _clone_command(env.openupgrade_url, version, ou_dest),
                )
            )
        if not env.uses_legacy_layout(version):
            odoo_dest = env.odoo_clone_dir(version)
            if not exists(odoo_dest):
                commands.append(
                    Command(
                        tf("Clone Odoo {}", version),
                        _clone_command(env.odoo_repo_url, version, odoo_dest),
                    )
                )
    return commands


def _setuptools_pin(version: str) -> str:
    """The extra install argument a migration step needs, or an empty string.
    (Its 13.0 build pin lives in that step's constraints file instead.)"""
    return f" '{SETUPTOOLS_PIN}'" if odoo_major(version) <= PKG_RESOURCES_LAST_MAJOR else ""


def _never_read(_path: Path) -> str | None:
    return None


def plan_migration_venvs(
    env: MigrationEnv, exists: Exists = _never, read: Read = _never_read
) -> list[Command]:
    """For each natively-run version: write the overrides file, build a uv venv with
    the matched interpreter, and install requirements (with ``--overrides`` repairs)
    + psycopg2-binary + openupgradelib. Every step in the chain gets one.

    Skips on the ready *marker*, not the venv directory: a venv whose installs
    failed midway has no marker and is rebuilt (``uv venv`` recreates in place).
    A ready venv is also rebuilt when its ``pyvenv.cfg`` (read through ``read``)
    names another interpreter than the step now resolves to — that is how a
    newly pinned Python takes effect."""
    commands: list[Command] = []
    for version in env.chain():
        python, _method = env.interpreter(version)
        if python is None:  # pragma: no cover - every version declares one
            continue
        if exists(env.venv_ready_marker(version)) and _venv_python(env, version, read) in (
            None, python
        ):
            continue
        if not commands:
            commands.append(
                Command(
                    tf("Create requirements directory"),
                    f"mkdir -p {shlex.quote(str(env.requirements_dir))}",
                )
            )
        # For the <= 13 layout the OpenUpgrade checkout *is* Odoo, so its own
        # requirements.txt is the one to install; there is no separate clone.
        requirements = (
            env.openupgrade_clone_dir(version) if env.uses_legacy_layout(version)
            else env.odoo_clone_dir(version)
        ) / "requirements.txt"
        commands += venv_commands(env, version, python, requirements)
    return commands


def venv_commands(
    env: MigrationEnv, version: str, python: str, requirements: Path, openupgrade: bool = True
) -> list[Command]:
    """Build one version's uv venv and install into it.

    Shared by the chain's steps and by the source version a demo seed needs,
    because they differ only in where the requirements come from and whether
    ``openupgradelib`` is wanted — and writing the recipe twice is how the two
    would come to disagree about an interpreter or an override.
    """
    venv = env.venv_dir(version)
    overrides = env.overrides_file(version)
    commands = write_text_file_command(
        overrides, templates.render_migration_overrides(version, python)
    )
    constraints_text = templates.render_migration_constraints(version)
    constraints = env.constraints_file(version)
    if constraints_text:
        commands += write_text_file_command(constraints, constraints_text)
    extra = f" openupgradelib{_setuptools_pin(version)}" if openupgrade else _setuptools_pin(version)
    commands += [
        Command(
            tf("Create uv venv (Python {}) for Odoo {}", python, version),
            f"uv venv --clear --no-project --python {shlex.quote(python)} "
            f"{shlex.quote(str(venv))}",
        ),
        Command(
            tf("Install Odoo {} requirements", version),
            f"uv pip install --python {shlex.quote(str(venv))} "
            f"-r {shlex.quote(str(requirements))} "
            f"--overrides {shlex.quote(str(overrides))}"
            + (
                f" --build-constraints {shlex.quote(str(constraints))}"
                if constraints_text
                else ""
            ),
        ),
        Command(
            tf("Install psycopg2-binary for Odoo {}", version),
            f"uv pip install --python {shlex.quote(str(venv))} psycopg2-binary{extra}",
        ),
        Command(
            tf("Mark Odoo {} venv as ready", version),
            f"touch {shlex.quote(str(env.venv_ready_marker(version)))}",
        ),
    ]
    return commands


def plan_migration_configs(
    env: MigrationEnv, read: Read = _unread, stamp: str = ""
) -> list[Command]:
    """Write the per-step odoo.conf and the run_migration.sh driver.

    A step's `odoo.conf` is the natural place to add `limit_time_real = 0` or an
    extra addons path while chasing a stuck step, and re-generating an environment
    is routine — so an existing file that would change is kept as
    ``<file>.bak-<stamp>`` first, exactly as the workspace surface does."""
    dirs: list[Path] = [env.conf_dir, env.checkpoints_dir, env.logs_dir, env.requirements_dir]
    for version in env.chain():
        dirs += [env.addons_custom_dir(version), env.addons_oca_dir(version)]
    private = [env.checkpoints_dir, env.logs_dir]
    commands: list[Command] = [
        Command(
            tf("Create migration directories"),
            "mkdir -p " + " ".join(shlex.quote(str(p)) for p in dirs)
            # A checkpoint is a `pg_dump` of the restored copy of a customer's
            # production database, and a log is Odoo's log for it. `chmod` rather
            # than `mkdir -m`, so an environment generated before this is narrowed
            # too — `mkdir -p` leaves an existing directory's mode alone.
            + " && chmod 700 " + " ".join(shlex.quote(str(p)) for p in private),
        )
    ]
    files = [
        (env.config_file(version), templates.render_migration_conf(env, version), "644")
        for version in env.chain()
    ]
    files.append((env.root / "run_migration.sh", templates.render_run_migration_sh(env), "755"))
    for path, content, mode in files:
        current = read(path)
        if current is not None and current.rstrip("\n") == content.rstrip("\n"):
            continue
        if current is not None:
            backup = Path(f"{path}.bak-{stamp}" if stamp else f"{path}.bak")
            commands.append(
                Command(
                    tf("Back up {} to {}", str(path), str(backup)),
                    f"cp -p {shlex.quote(str(path))} {shlex.quote(str(backup))}",
                )
            )
        commands += write_text_file_command(path, content, mode)
    return commands



def _venv_python(env: MigrationEnv, version: str, read: Read) -> str | None:
    """The ``3.N`` a step's venv was built with, from its ``pyvenv.cfg``; None when
    it cannot be read (a ready venv is then kept, as before this check existed)."""
    text = read(env.venv_dir(version) / "pyvenv.cfg")
    choice = interpreter_from_pyvenv(version, text) if text else None
    return choice.python if choice else None


def plan_migration_oca(
    env: MigrationEnv, exists: Exists = _never, versions: list[str] | None = None
) -> list[Command]:
    """Clone each named OCA repository per version and link it into that
    version's ``oca`` directory.

    ``versions`` defaults to the chain's steps. A demo seed passes the *source*
    version, which is not a step and therefore gets no OCA link otherwise — and a
    module that is not on disk at the source version cannot be installed there.

    A repository OCA has not ported to a version is a fact the operator needs,
    not a reason to refuse to build the environment: the branch is asked for
    first, and its absence is reported while the step's directory stays empty.
    Nothing else is masked — a clone that fails for any other reason still fails
    the step.
    """
    commands: list[Command] = []
    for repo in env.oca_repos:
        url = f"{WorkspaceConfig.oca_url_base}/{repo}.git"
        for version in versions if versions is not None else env.chain():
            dest = env.oca_clone_dir(repo, version)
            link = env.oca_link_dir(repo, version)
            if not exists(dest):
                commands.append(
                    Command(
                        tf("Clone OCA {} ({}) into the shared cache", repo, version),
                        f"if git ls-remote --exit-code --heads {shlex.quote(url)} "
                        f"{shlex.quote(version)} >/dev/null 2>&1; then "
                        f"{_clone_command(url, version, dest)}; "
                        f"else echo {shlex.quote(f'OCA {repo} has no {version} branch — that step has no OCA source for it')}; "
                        f"fi",
                    )
                )
            commands.append(
                Command(
                    tf("Link OCA {} for Odoo {}", repo, version),
                    f"mkdir -p {shlex.quote(str(link.parent))} && "
                    # Only when the clone is there: an unported repository leaves
                    # no link rather than one pointing at nothing.
                    f"if [ -d {shlex.quote(str(dest))} ]; then "
                    f"ln -sfnT {shlex.quote(str(dest))} {shlex.quote(str(link))}; fi",
                )
            )
    return commands


def plan_generate_migration(
    env: MigrationEnv, exists: Exists = _never, read: Read = _never_read, stamp: str = ""
) -> list[Command]:
    """Full migration-environment plan: clones + uv venvs + configs + driver."""
    return (
        plan_migration_clones(env, exists)
        + plan_migration_oca(env, exists)
        + plan_migration_venvs(env, exists, read)
        # The same reader: a hand-tuned step config is kept as .bak-<stamp>.
        + plan_migration_configs(env, read, stamp)
    )


# Validated on WSL (2026-07-18): staged a sample module 16→18 (tree→list applied,
# version bumps, per-step logs). Pinned for reproducibility; bump deliberately.
STAGING_TOOL_SPEC = "odoo-module-migrator==0.5.0"


def plan_staging_tool(env: MigrationEnv) -> list[Command]:
    """Install `odoo-module-migrator` (OCA) into a shared uv tool venv — a host
    prerequisite prepared through the plan, never a runtime dependency of
    odoo_dwg."""
    venv = env.staging_tool_venv
    return [
        Command(
            tf("Create the staging tool venv"),
            f"uv venv --clear --no-project {shlex.quote(str(venv))}",
        ),
        Command(
            tf("Install odoo-module-migrator"),
            f"uv pip install --python {shlex.quote(str(venv))} {STAGING_TOOL_SPEC}",
        ),
    ]


def plan_promote_module(
    env: MigrationEnv,
    module: str,
    versions: list[str],
    into: PromotedModules,
) -> list[Command]:
    """Copy a module's reviewed code, for each named step, to the durable location.

    Copy and not move: the environment stays runnable after a promotion, and a
    promotion is not a point of no return — the durable copy can be discarded and
    made again. The cost is that the two can drift, which the staging report
    names rather than prevents; preventing it would mean locking the copy the
    operator actually works in.

    The staged directory carries the throwaway git repository the migrator needs;
    it is not copied, because the durable location's history is the operator's.
    """
    commands: list[Command] = []
    for version in versions:
        source = env.addons_custom_dir(version) / module
        target = into.module_dir(version, module)
        parent = into.version_dir(version)
        commands.append(
            Command(
                tf("Promote {} {} to {}", module, version, str(target)),
                f"mkdir -p {shlex.quote(str(parent))} && "
                f"rm -rf {shlex.quote(str(target))} && "
                f"cp -a {shlex.quote(str(source))} {shlex.quote(str(parent))}/ && "
                f"rm -rf {shlex.quote(str(target / '.git'))}",
            )
        )
    return commands


def plan_stage_module(
    env: MigrationEnv,
    module: str,
    source_dir: Path,
    promoted: PromotedModules | None = None,
    exists: Exists = _never,
) -> list[Command]:
    """Stage one custom module stepwise: the operator's source copy feeds the
    first step, each later step consumes the previous step's staged output, and
    `odoo-module-migrate` applies exactly that bump in place. The operator's
    source directory is never modified. Existing staged targets are replaced —
    the workflow gates that behind an exact-phrase confirmation.

    A step whose code has been **promoted** takes it from there instead, and runs
    no migrator: that code is already at that version and has been reviewed. This
    is what makes a final run apply proven work rather than derive it a second
    time. A chain with nothing promoted plans exactly what it always did.
    """
    migrate_bin = env.staging_tool_venv / "bin" / "odoo-module-migrate"
    commands: list[Command] = [
        Command(
            tf("Create staging directories for {}", module),
            "mkdir -p " + " ".join(
                shlex.quote(str(p))
                for p in [env.staging_dir] + [env.addons_custom_dir(v) for v in env.chain()]
            ),
        )
    ]
    previous = Path(source_dir) / module
    previous_version = env.source
    for version in env.chain():
        target_parent = env.addons_custom_dir(version)
        target = target_parent / module
        log = env.staging_log_file(module, version)
        kept = promoted.module_dir(version, module) if promoted else None
        if kept is not None and exists(kept):
            # Reviewed code for this step: copy it in and derive nothing. The
            # report says so, because a step that was not derived is a step whose
            # warnings this run will not show.
            commands.append(
                Command(
                    tf("Take {} stage {} from the promoted copy", module, version),
                    f"rm -rf {shlex.quote(str(target))} && "
                    f"cp -a {shlex.quote(str(kept))} {shlex.quote(str(target_parent))}/",
                )
            )
            previous = target
            previous_version = version
            continue
        commands += [
            Command(
                tf("Copy {} stage {} from the {} stage", module, version, previous_version),
                f"rm -rf {shlex.quote(str(target))} && "
                f"cp -a {shlex.quote(str(previous))} {shlex.quote(str(target_parent))}/",
            ),
            # odoo-module-migrate runs git commands over the directory (verified:
            # it fails with "not a git repository" otherwise), so each stage dir
            # is a throwaway git worktree with the pre-migration state committed.
            Command(
                tf("Prepare the git worktree for {} stage {}", module, version),
                f"git -C {shlex.quote(str(target_parent))} init -q && "
                f"git -C {shlex.quote(str(target_parent))} add -A && "
                f"git -C {shlex.quote(str(target_parent))} "
                # Independent of the operator's git config, all of it: a global
                # `commit.gpgsign = true` fails this throwaway commit outright
                # (git exits 128, since the interpolated identity has no key),
                # and a global hook has no business running on it either.
                f"-c user.name=odoo-dwg -c user.email=odoo-dwg@localhost "
                f"-c core.hooksPath=/dev/null "
                f"commit -qm {shlex.quote(f'stage {module} {version} input')} "
                f"--allow-empty --no-gpg-sign --no-verify",
            ),
            Command(
                tf("Migrate {} code {} -> {}", module, previous_version, version),
                f"set -o pipefail && {shlex.quote(str(migrate_bin))} "
                f"--directory {shlex.quote(str(target_parent))} "
                f"--modules {shlex.quote(module)} "
                f"--init-version-name {shlex.quote(previous_version)} "
                f"--target-version-name {shlex.quote(version)} "
                f"2>&1 | tee {shlex.quote(str(log))}",
            ),
        ]
        previous = target
        previous_version = version
    return commands


def plan_clean_migration(root: Path, repos_dir: Path | None = None) -> list[Command]:
    """Remove one migration environment directory (venvs, confs, checkpoints, logs,
    requirements, driver). With ``repos_dir``, also remove the shared clones cache —
    note that cache serves every migration environment under the base directory.

    Destructive: the workflow gates this behind preview + an exact-phrase
    confirmation. The PostgreSQL migration database is host state, not files, and
    is deliberately not part of this plan."""
    commands = [
        Command(
            tf("Remove migration environment {}", str(root)),
            f"rm -rf {shlex.quote(str(root))}",
        )
    ]
    if repos_dir is not None:
        commands.append(
            Command(
                tf("Remove shared migration clones {}", str(repos_dir)),
                f"rm -rf {shlex.quote(str(repos_dir))}",
            )
        )
    return commands


def plan_refresh_repos(cfg: WorkspaceConfig, exists: Exists = _never) -> list[Command]:
    """Fast-forward-pull every present clone in the shared cache for this
    workspace's versions/OCA repos. Absent clones are skipped (nothing to refresh)."""
    commands: list[Command] = []
    for version in cfg.versions:
        dest = cfg.odoo_clone_dir(version)
        if exists(dest):
            commands.append(
                Command(
                    tf("Refresh Odoo {}", version),
                    f"git -C {shlex.quote(str(dest))} pull --ff-only",
                )
            )
    for repo in cfg.oca_repos:
        for version in cfg.versions:
            dest = cfg.oca_clone_dir(repo, version)
            if exists(dest):
                commands.append(
                    Command(
                        tf("Refresh OCA {} ({})", repo, version),
                        f"git -C {shlex.quote(str(dest))} pull --ff-only",
                    )
                )
    return commands


def plan_generate_workspace(
    cfg: WorkspaceConfig,
    exists: Exists = _never,
    interpreters: dict[str, InterpreterChoice] | None = None,
) -> list[Command]:
    """Full create plan: shared repo cache (skipping present clones), the workspace
    tree, then a venv build for each version whose venv is not already present. Pure
    — existence is injected; the workflow passes ``Path.exists`` and enforces the
    create-only guard (refusing to clobber an existing workspace).

    ``interpreters`` maps a version to the interpreter its venv must be built with
    (resolved against the support matrix by the workflow, which is what probes the
    host); versions absent from it use the host ``python3``."""
    commands = plan_repo_cache(cfg, exists)
    commands += plan_workspace_tree(cfg, interpreters)
    for version in cfg.versions:
        if not exists(cfg.venv_ready_marker(version)):
            commands += plan_build_venv(
                cfg, version, interpreter=(interpreters or {}).get(version)
            )
    return commands


def plan_build_venv(
    cfg: WorkspaceConfig,
    version: str,
    recreate: bool = False,
    interpreter: InterpreterChoice | None = None,
) -> list[Command]:
    """Build one instance venv and install its version-matched requirements.

    ``recreate`` removes an existing venv first (management "regenerate"); by
    default it does not, so generation can skip versions whose venv already exists
    by simply not calling this.

    ``interpreter`` is the resolved choice for this version. A ``uv``-provided
    interpreter is created with ``uv venv --seed``, which seeds ``pip`` so every
    following step — and everything the generated workspace documents — is
    identical to a stdlib venv. Without it, the host ``python3`` is used.
    """
    venv = cfg.venv_dir(version)
    odoo = cfg.odoo_clone_dir(version)
    commands: list[Command] = []
    if recreate:
        commands.append(
            Command(tf("Remove existing venv {}", str(venv)), f"rm -rf {shlex.quote(str(venv))}")
        )
    if interpreter and interpreter.source == UV_PYTHON and interpreter.python:
        create = Command(
            tf("Create venv {} with uv (Python {})", str(venv), interpreter.python),
            f"uv venv --seed --no-project --python {shlex.quote(interpreter.python)} "
            f"{shlex.quote(str(venv))}",
        )
    else:
        create = Command(
            tf("Create venv {}", str(venv)),
            f"python3 -m venv {shlex.quote(str(venv))}",
        )
    commands += [
        create,
        Command(
            tf("Upgrade pip/wheel/setuptools in {}", str(venv)),
            f"{shlex.quote(str(venv / 'bin' / 'pip'))} install --upgrade pip wheel "
            f"{shlex.quote(setuptools_requirement(version))}",
        ),
        Command(
            tf("Install Odoo {} requirements", version),
            templates.requirements_install_command(
                str(venv / "bin" / "pip"), str(odoo / "requirements.txt"), version
            ),
        ),
        # Last, so the marker means "every install above finished".
        Command(
            tf("Mark the venv {} ready", str(venv)),
            f"touch {shlex.quote(str(cfg.venv_ready_marker(version)))}",
        ),
    ]
    return commands


def plan_generate_tester(
    env: MigrationEnv, probes: list, uncovered: list[str]
) -> list[Command]:
    """Write the rehearsal tester into every step's ``addons/odoo<major>/custom``.

    Into the environment and nowhere else: the module is a rehearsal instrument,
    and its manifest says so. Each step gets the same tree, so the module is
    present whichever step the operator stops at.
    """
    chain = f"{env.source} - {env.target}"
    files = templates.render_tester_module(probes, uncovered, chain)
    commands: list[Command] = []
    for version in env.chain():
        root = env.addons_custom_dir(version) / tester.TESTER_MODULE
        directories = sorted({str((root / path).parent) for path in files})
        commands.append(
            Command(
                tf("Create the tester tree for {}", version),
                "mkdir -p " + " ".join(shlex.quote(d) for d in directories),
            )
        )
        for path, content in files.items():
            commands += write_text_file_command(root / path, content)
    return commands


def plan_seed_environment(env: MigrationEnv, exists: Exists = _never) -> list[Command]:
    """Prepare the **source** version, which the chain itself never builds.

    ``env.chain()`` is the steps — 13.0 … 19.0 for a 12 → 19 chain — so an
    environment has no clone, venv or config for 12.0 at all. It does not need
    one to migrate: the source arrives as a dump. It needs one to *make* that
    dump, and what it needs is plain Odoo, not OpenUpgrade — there is no
    OpenUpgrade 12.0 branch, the 12 → 13 step runs OpenUpgrade 13.
    """
    version = env.source
    commands: list[Command] = []
    clone = env.odoo_clone_dir(version)
    if not exists(clone):
        commands.append(
            Command(tf("Clone Odoo {}", version), _clone_command(env.odoo_repo_url, version, clone))
        )
    python, _method = env.interpreter(version)
    if python is not None and not exists(env.venv_ready_marker(version)):
        commands.append(
            Command(
                tf("Create requirements directory"),
                f"mkdir -p {shlex.quote(str(env.requirements_dir))}",
            )
        )
        # openupgradelib is not installed: the source version never runs a
        # migration script, it only builds a database that will be dumped.
        commands += venv_commands(
            env, version, python, clone / "requirements.txt", openupgrade=False
        )
    # The source version is not a step, so the chain's OCA linking skips it.
    commands += plan_migration_oca(env, exists, versions=[version])
    commands.append(
        Command(
            tf("Create the source add-ons directories for {}", version),
            "mkdir -p "
            + " ".join(
                shlex.quote(str(p))
                for p in (env.addons_custom_dir(version), env.addons_oca_dir(version))
            ),
        )
    )
    commands += write_text_file_command(env.config_file(version), templates.render_seed_conf(env))
    return commands


def plan_seed_demo(env: MigrationEnv, modules: list[str]) -> list[Command]:
    """Write the seed script. Running it is the operator's, like the driver's.

    Not applied directly: building a demo database installs modules one by one
    and can take many minutes, and a plan step that long belongs in a script the
    operator can re-run, read and interrupt.
    """
    for module in modules:
        if not MODULE_NAME_RE.fullmatch(module):
            raise ValueError(tf("Invalid module name: {}", module))
    script = env.root / "seed_demo.sh"
    return write_text_file_command(script, templates.render_seed_demo_sh(env, modules), "755")
