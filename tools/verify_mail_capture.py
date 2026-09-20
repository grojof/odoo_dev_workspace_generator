#!/usr/bin/env python3
"""Execute capture → check → restore against a throwaway PostgreSQL.

The unit suite asserts the SQL's *text* (it may not touch a database), and that
is how a capture that switched off its own Mailpit server on the second run got
written: the statement read correctly. This one runs it.

It builds two `ir_mail_server` tables that differ the way Odoo's differ across
the chain — a 12-era one without `smtp_authentication`, a 19-era one where that
column is `NOT NULL` — and asserts what the operator depends on:

- the client's row comes back from restore byte for byte, credentials included;
- a mail server the client had switched off is not switched on by restore;
- a second capture leaves the capture's own server active;
- the added server satisfies whatever columns that version requires;
- restore leaves no table of ours behind, and refuses a database never captured.

    python tools/verify_mail_capture.py

Needs a PostgreSQL server binary (`/usr/lib/postgresql/*/bin`). No network, no
root, nothing outside a temporary directory, and it never touches the host's
cluster.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odoo_dwg import egress  # noqa: E402

# The columns Odoo requires change across the chain; the capture must not care.
SCHEMAS: dict[str, str] = {
    "12-era (no smtp_authentication)": """
        CREATE TABLE ir_mail_server (
          id serial NOT NULL PRIMARY KEY, name varchar NOT NULL,
          smtp_host varchar NOT NULL, smtp_port integer NOT NULL,
          smtp_encryption varchar NOT NULL, smtp_user varchar, smtp_pass varchar,
          sequence integer, active boolean,
          create_uid integer, create_date timestamp);
        INSERT INTO ir_mail_server
          (name, smtp_host, smtp_port, smtp_encryption, smtp_user, smtp_pass, sequence, active)
        VALUES ('Client SMTP', 'smtp.client.example', 587, 'starttls',
                'postmaster', 's3cret', 10, true),
               ('Deliberately off', 'smtp.old.example', 25, 'none', NULL, NULL, 20, false);
    """,
    "19-era (smtp_authentication NOT NULL)": """
        CREATE TABLE ir_mail_server (
          id serial NOT NULL PRIMARY KEY, name varchar NOT NULL,
          smtp_host varchar NOT NULL, smtp_port integer NOT NULL,
          smtp_encryption varchar NOT NULL, smtp_authentication varchar NOT NULL,
          from_filter varchar, smtp_user varchar, smtp_pass varchar,
          sequence integer, active boolean);
        CREATE TABLE fetchmail_server (id serial PRIMARY KEY, name varchar, active boolean);
        INSERT INTO ir_mail_server
          (name, smtp_host, smtp_port, smtp_encryption, smtp_authentication,
           smtp_user, smtp_pass, sequence, active)
        VALUES ('Client SMTP', 'smtp.client.example', 587, 'starttls', 'certificate',
                'postmaster', 's3cret', 10, true),
               ('Deliberately off', 'smtp.old.example', 25, 'none', 'login', NULL, NULL, 20, false);
        INSERT INTO fetchmail_server (name, active) VALUES ('IMAP inbox', true);
    """,
}
# The whole client row, so restore is checked on every column and not on the
# handful this tool remembered to name.
CLIENT_ROW = (
    "SELECT to_jsonb(s) FROM ir_mail_server s WHERE name = 'Client SMTP'"
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _bindir() -> Path | None:
    candidates = sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True)
    return candidates[0] if candidates else None


class Cluster:
    """A cluster of our own: its own data directory, port and socket.

    The socket lives under /tmp and not in the temp tree, because a unix socket
    path over 107 bytes is refused and the session's temp directory is longer
    than that.
    """

    def __init__(self, root: Path, bindir: Path) -> None:
        self.data = root / "data"
        self.bin = bindir
        self.port = _free_port()
        self.sock = Path(tempfile.mkdtemp(prefix="/tmp/odwg-mail-"))

    def start(self) -> None:
        subprocess.run(
            [str(self.bin / "initdb"), "-D", str(self.data), "-U", "postgres",
             "--auth=trust", "--no-sync"],
            check=True, capture_output=True, text=True,
        )
        subprocess.run(
            [str(self.bin / "pg_ctl"), "-D", str(self.data), "-w", "-l",
             str(self.data.parent / "pg.log"), "-o",
             f"-p {self.port} -k {self.sock} -c listen_addresses=", "start"],
            check=True, capture_output=True, text=True,
        )

    def stop(self) -> None:
        subprocess.run(
            [str(self.bin / "pg_ctl"), "-D", str(self.data), "-m", "immediate", "-w", "stop"],
            check=False, capture_output=True, text=True,
        )
        # The socket directory is outside the temp tree — a unix socket path over
        # 107 bytes is refused and the session temp directory is longer — so
        # nothing else removes it. Twenty-three were left in /tmp before this.
        shutil.rmtree(self.sock, ignore_errors=True)

    def sql(self, query: str, db: str = "postgres") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.bin / "psql"), "-X", "-h", str(self.sock), "-p", str(self.port),
             "-U", "postgres", "-d", db, "-w", "-v", "ON_ERROR_STOP=1", "-tAF\t", "-c", query],
            capture_output=True, text=True,
        )

    def value(self, query: str, db: str) -> str:
        result = self.sql(query, db)
        if result.returncode != 0:
            raise SystemExit(f"query failed: {query}\n{result.stderr.strip()}")
        return result.stdout.strip()


def main() -> int:
    bindir = _bindir()
    if bindir is None:
        print("No PostgreSQL server binaries found under /usr/lib/postgresql.")
        return 1

    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        print(f"{'ok  ' if condition else 'FAIL'}  {label}")
        if not condition:
            failures.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory(prefix="odwg-mail-") as tmp:
        cluster = Cluster(Path(tmp), bindir)
        cluster.start()
        try:
            for index, (label, schema) in enumerate(SCHEMAS.items()):
                db = f"probe{index}"
                cluster.sql(f"CREATE DATABASE {db}")
                if (setup := cluster.sql(schema, db)).returncode != 0:
                    raise SystemExit(f"fixture failed: {setup.stderr.strip()}")
                before = cluster.value(CLIENT_ROW, db)

                captured = cluster.sql(egress.mail_capture_sql(), db)
                check(f"{label}: capture runs", captured.returncode == 0, captured.stderr.strip())
                check(
                    f"{label}: the client's server is deactivated, not altered",
                    cluster.value(
                        "SELECT active::text FROM ir_mail_server WHERE name = 'Client SMTP'", db
                    ) == "false"
                    and cluster.value(
                        "SELECT smtp_host || ':' || coalesce(smtp_user, '') || ':' "
                        "|| coalesce(smtp_pass, '') FROM ir_mail_server "
                        "WHERE name = 'Client SMTP'", db
                    ) == "smtp.client.example:postmaster:s3cret",
                    cluster.value(CLIENT_ROW, db),
                )
                check(
                    f"{label}: a server pointing at the capture is active and preferred",
                    cluster.value(
                        "SELECT smtp_host || ':' || smtp_port::text FROM ir_mail_server "
                        "WHERE active ORDER BY sequence LIMIT 1", db
                    ) == f"{egress.MAILPIT_SMTP_HOST}:{egress.MAILPIT_SMTP_PORT}",
                    cluster.value(
                        "SELECT string_agg(name || '=' || active::text, ', ' ORDER BY id) "
                        "FROM ir_mail_server", db),
                )

                # The reading the check action does, against the real rows.
                state = egress.read_mail_state([
                    row.split("\t")
                    for row in cluster.value(
                        egress.mail_state_sql(
                            fetchmail=cluster.value(
                                "SELECT (to_regclass('fetchmail_server') IS NOT NULL)::text", db
                            ) == "true",
                            captured=True,
                        ), db).splitlines()
                ])
                check(
                    f"{label}: the check reads a captured database as unable to mail out",
                    state.captured and not state.escaping and not state.falls_back_to_config
                    and state.fetchmail_active == 0,
                    str(state),
                )

                second = cluster.sql(egress.mail_capture_sql(), db)
                check(
                    f"{label}: capturing twice leaves the capture active",
                    second.returncode == 0
                    and cluster.value(
                        "SELECT count(*)::text FROM ir_mail_server WHERE active "
                        f"AND smtp_host = '{egress.MAILPIT_SMTP_HOST}'", db) == "1",
                    second.stderr.strip() or cluster.value(
                        "SELECT string_agg(name || '=' || active::text, ', ' ORDER BY id) "
                        "FROM ir_mail_server", db),
                )

                restored = cluster.sql(egress.mail_restore_sql(), db)
                check(f"{label}: restore runs", restored.returncode == 0, restored.stderr.strip())
                check(
                    f"{label}: the client's row comes back exactly as it was",
                    cluster.value(CLIENT_ROW, db) == before,
                    f"before={before}\nafter={cluster.value(CLIENT_ROW, db)}",
                )
                check(
                    f"{label}: a server the client had switched off stays off",
                    cluster.value(
                        "SELECT active::text FROM ir_mail_server WHERE name = 'Deliberately off'",
                        db) == "false",
                    "restore switched on a server it never switched off",
                )
                check(
                    f"{label}: the capture's own server is gone",
                    cluster.value(
                        "SELECT count(*)::text FROM ir_mail_server WHERE smtp_host = "
                        f"'{egress.MAILPIT_SMTP_HOST}'", db) == "0",
                    "the added server was left behind",
                )
                check(
                    f"{label}: no table of ours is left in the database",
                    cluster.value(
                        f"SELECT (to_regclass('{egress.CAPTURE_RECORD_TABLE}') IS NULL)::text",
                        db) == "true",
                    "the record table survived restore",
                )
                again = cluster.sql(egress.mail_restore_sql(), db)
                check(
                    f"{label}: restoring a database that was never captured is refused",
                    again.returncode != 0 and "no mail capture is recorded" in again.stderr,
                    again.stderr.strip(),
                )

            # Fetchmail only exists in the second fixture; check it came back.
            check(
                "fetchmail is fetching again after restore",
                cluster.value("SELECT active::text FROM fetchmail_server", "probe1") == "true",
                "fetchmail stayed off",
            )

            # A database with no mail server at all: nothing to clone, and Odoo
            # already falls back to its configuration file.
            cluster.sql("CREATE DATABASE probe_empty")
            cluster.sql(
                "CREATE TABLE ir_mail_server (id serial PRIMARY KEY, name varchar NOT NULL, "
                "smtp_host varchar NOT NULL, smtp_port integer NOT NULL, "
                "smtp_encryption varchar NOT NULL, smtp_user varchar, smtp_pass varchar, "
                "sequence integer, active boolean)", "probe_empty")
            empty = cluster.sql(egress.mail_capture_sql(), "probe_empty")
            check(
                "a database with no mail server is captured without inventing one",
                empty.returncode == 0
                and cluster.value("SELECT count(*)::text FROM ir_mail_server", "probe_empty") == "0",
                empty.stderr.strip(),
            )
            state = egress.read_mail_state([
                row.split("\t")
                for row in cluster.value(
                    egress.mail_state_sql(fetchmail=False, captured=True), "probe_empty"
                ).splitlines()
            ])
            check(
                "and the check reports it as falling back to the configuration file",
                state.falls_back_to_config and not state.escaping,
                str(state),
            )
        finally:
            cluster.stop()

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("\nCapture, check and restore behave as documented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
