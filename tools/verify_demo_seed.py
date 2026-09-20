#!/usr/bin/env python3
"""Execute the generated ``seed_demo.sh`` against stub binaries.

A demo seed is the only way to rehearse a chain before a client's dump exists,
so it has one job: either it produces a dump the driver accepts, or it says
which module stopped it. Asserting its *text* would not tell the difference —
`run_migration.sh` taught this project that, when a checkpoint reported success
after a failed `pg_dump`.

This renders a 12.0 -> 19.0 environment into a throwaway directory, puts stub
`createdb`/`psql`/`pg_dump` and a stub Odoo interpreter on PATH, and checks what
the script actually does.

    python tools/verify_demo_seed.py

Host-only (needs bash), no network, no PostgreSQL, no Odoo, nothing outside its
temporary directory.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odoo_dwg import templates  # noqa: E402
from odoo_dwg.models import MigrationEnv  # noqa: E402

SOURCE, TARGET = "12.0", "19.0"
MODULES = ["partner_firstname", "website_sale_product_style_badge"]


def _stub(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _build(
    root: Path, *, failing_module: str = "", existing_db: bool = False, failing_dump: bool = False
) -> tuple[Path, MigrationEnv, Path]:
    MigrationEnv.base_dir = str(root / "envs")
    env = MigrationEnv(source=SOURCE, target=TARGET)
    script = root / "seed_demo.sh"
    script.write_text(templates.render_seed_demo_sh(env, MODULES), encoding="utf-8")
    script.chmod(0o755)

    stubs = root / "bin"
    _stub(stubs / "createdb", 'echo "createdb $*" >> "$CALLS"')
    # `psql -lqt` is how the script asks whether the database is already there.
    # The stub refuses a call with no -U, the way a real psql does when the OS
    # user has no role of their own ("FATAL: role ... does not exist"). Without
    # that, a check missing its connection arguments passed here and silently
    # found nothing on a real host — the existence check never fired.
    _stub(
        stubs / "psql",
        'case " $* " in *" -U "*) ;; '
        '*) echo "psql: FATAL: role does not exist" >&2; exit 2 ;; esac\n'
        + (f'echo "{env.source_database}|x|y"' if existing_db else 'echo "postgres|x|y"'),
    )
    # A failing pg_dump writes part of its output first, the way a real one
    # interrupted does. Failing without writing made the "leaves nothing behind"
    # check pass against a script that left the partial file.
    _stub(
        stubs / "pg_dump",
        'echo "partial" > "${@: -2:1}"; exit 1' if failing_dump
        else 'echo "dump" > "${@: -2:1}"; echo "pg_dump $*" >> "$CALLS"',
    )
    # The step's interpreter: it records the module it was asked to install, and
    # fails for the one the case names.
    interpreter = env.venv_dir(SOURCE) / "bin" / "python"
    _stub(
        interpreter,
        'echo "odoo $*" >> "$CALLS"\n'
        + (f'for a in "$@"; do [ "$a" = "{failing_module}" ] && exit 1; done\n'
           if failing_module else "")
        + "exit 0",
    )
    # The *plain* clone, which is what a seed runs. Building this fixture from
    # `env.odoo_bin(SOURCE)` made the stub agree with the product's own wrong
    # assumption — it created `openupgrade-12.0/odoo-bin`, a path that cannot
    # exist, and the precondition passed here while failing on a real host.
    odoo_bin = Path(env.source_odoo_bin)
    odoo_bin.parent.mkdir(parents=True, exist_ok=True)
    odoo_bin.write_text("", encoding="utf-8")
    Path(env.logs_dir).mkdir(parents=True, exist_ok=True)
    Path(env.conf_dir).mkdir(parents=True, exist_ok=True)
    return script, env, stubs


def _run(root: Path, script: Path, stubs: Path) -> tuple[subprocess.CompletedProcess[str], str]:
    calls = root / "calls"
    result = subprocess.run(
        ["bash", str(script)],
        cwd=root,
        capture_output=True,
        text=True,
        env={"PATH": f"{stubs}:/usr/bin:/bin", "HOME": str(root), "CALLS": str(calls)},
    )
    return result, calls.read_text(encoding="utf-8") if calls.exists() else ""


def main() -> int:
    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        print(f"{'ok  ' if condition else 'FAIL'}  {label}")
        if not condition:
            failures.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory(prefix="odwg-seed-") as tmp:
        root = Path(tmp)
        script, env, stubs = _build(root)
        result, calls = _run(root, script, stubs)
        check("a fresh seed runs to completion", result.returncode == 0,
              result.stdout + result.stderr)
        check(
            "it produces the dump the driver takes",
            Path(env.source_dump_file).exists() and "-Fc" in calls,
            calls,
        )
        check(
            "and leaves no half-written dump beside it",
            not list(Path(env.root).glob("*.tmp")),
            str(list(Path(env.root).glob("*"))),
        )
        check(
            "base is installed before any other module",
            calls.index("-i base") < min(calls.index(f"-i {m}") for m in MODULES),
            calls,
        )
        check(
            "every chosen module is installed, one call each",
            all(calls.count(f"-i {module}") == 1 for module in MODULES),
            calls,
        )
        check(
            "the demo flag is not passed, because <= 18.0 loads demo by default",
            "--without-demo" not in calls,
            calls,
        )
        check(
            "it tells the operator how to run the chain",
            "run_migration.sh" in result.stdout,
            result.stdout,
        )

        # Seeding again must not overwrite a dump the checkpoints may be against.
        again, _ = _run(root, script, stubs)
        check(
            "a second seed refuses rather than replacing the dump",
            again.returncode != 0 and "remove it to seed again" in again.stderr,
            again.stderr,
        )

    # A module that will not install names itself, and no dump is produced.
    with tempfile.TemporaryDirectory(prefix="odwg-seed-") as tmp:
        root = Path(tmp)
        script, env, stubs = _build(root, failing_module=MODULES[1])
        result, calls = _run(root, script, stubs)
        check(
            "a module that will not install is named",
            result.returncode != 0 and MODULES[1] in result.stderr,
            result.stdout + result.stderr,
        )
        check(
            "and no dump is produced from a database missing it",
            not Path(env.source_dump_file).exists() and "pg_dump" not in calls,
            calls,
        )

    # An existing database is not silently reused: its contents are unknown.
    with tempfile.TemporaryDirectory(prefix="odwg-seed-") as tmp:
        root = Path(tmp)
        script, env, stubs = _build(root, existing_db=True)
        result, _ = _run(root, script, stubs)
        check(
            "an existing database is refused, not reused",
            result.returncode != 0 and "drop it to seed again" in result.stderr,
            result.stdout + result.stderr,
        )

    # A dump that cannot be written must fail, not leave an empty file behind.
    with tempfile.TemporaryDirectory(prefix="odwg-seed-") as tmp:
        root = Path(tmp)
        script, env, stubs = _build(root, failing_dump=True)
        result, _ = _run(root, script, stubs)
        check(
            "a dump that fails stops the seed",
            result.returncode != 0 and "pg_dump failed" in result.stderr,
            result.stdout + result.stderr,
        )
        leftovers = sorted(p.name for p in Path(env.root).glob("source-*"))
        check(
            "and leaves neither a dump nor a half-written one",
            not leftovers,
            f"left behind: {leftovers}",
        )

    # Preconditions: no venv, no clone.
    with tempfile.TemporaryDirectory(prefix="odwg-seed-") as tmp:
        root = Path(tmp)
        script, env, stubs = _build(root)
        (env.venv_dir(SOURCE) / "bin" / "python").unlink()
        result, _ = _run(root, script, stubs)
        check(
            "the seed never looks for an OpenUpgrade checkout of the source",
            "openupgrade-" + SOURCE not in script.read_text(encoding="utf-8"),
            "the seed names a checkout that does not exist for the source version",
        )
        check(
            "no source venv stops the seed with what to do",
            result.returncode != 0 and "generate the environment first" in result.stderr,
            result.stdout + result.stderr,
        )

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("\nThe demo seed behaves as documented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
