#!/usr/bin/env python3
"""Execute the generated ``run_migration.sh`` against stub binaries.

The unit suite asserts the driver's *text* (it may not shell out), which is how a
checkpoint that reported success after a failed ``pg_dump`` survived two hardening
rounds. This tool runs the real script instead: it renders a 16.0 → 18.0
environment into a throwaway directory, puts stub ``psql``/``pg_dump``/
``pg_restore``/``dropdb``/``createdb``/``uv`` and per-step interpreters on PATH,
and checks what the driver actually does.

    python tools/verify_migration_driver.py

Host-only (needs bash), no network, no PostgreSQL, nothing outside its temp
directory. Exits non-zero on the first case that does not behave as documented.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odoo_dwg import templates  # noqa: E402
from odoo_dwg.models import (  # noqa: E402
    MigrationEnv,
    ModuleDecision,
    decisions_to_json,
)

SOURCE, TARGET = "16.0", "18.0"
# A chain that crosses the <= 13 layout, so the legacy step command and its own
# preconditions are executed too, not only the upgrade-path ones.
LEGACY_SOURCE, LEGACY_TARGET = "12.0", "14.0"


def _stub(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _build(
    root: Path,
    *,
    failing_pg_dump: bool = False,
    failing_step: str | None = None,
    source: str = SOURCE,
    target: str = TARGET,
    absorbed: tuple[str, str] | None = None,
) -> tuple[Path, MigrationEnv]:
    """Render the driver and the stub host it runs against."""
    MigrationEnv.base_dir = str(root / "envs")
    env = MigrationEnv(source=source, target=target)
    script = root / "run_migration.sh"
    script.write_text(templates.render_run_migration_sh(env), encoding="utf-8")

    stubs = root / "bin"
    # One installed module authored by Odoo: coverage warns, never blocks.
    listing = 'printf "base\\tOdoo S.A.\\n"'
    if absorbed:
        # One module of somebody else's, which the first step absorbs into
        # another. Odoo's own modules are only ever warned about.
        #
        # The database *changes* as the chain runs: once the first step has
        # migrated, the module answers to its successor's name. A stub that
        # answered the same thing at every step could not represent that, and
        # made the per-step coverage check look wrong when it was right.
        listing += (
            f'; if [ -e "$STATE/{env.chain()[0]}" ]; '
            f'then printf "{absorbed[1]}\\tACME\\n"; '
            f'else printf "{absorbed[0]}\\tACME\\n"; fi'
        )
    _stub(stubs / "psql",
          f'if [[ "$*" == *base* && "$*" == *latest_version* ]]; then echo {source}.1.0; '
          f'else {listing}; fi')
    for name in ("pg_restore", "dropdb", "createdb", "uv"):
        _stub(stubs / name, "exit 0")
    _stub(stubs / "pg_dump", "exit 1" if failing_pg_dump else 'echo "dump of $*"')
    for version in env.chain():
        # A step's interpreter, and one that fails after writing to its log.
        if version == failing_step:
            _stub(
                env.venv_dir(version) / "bin" / "python",
                f'echo "traceback" >> {env.logs_dir}/{version}.log; exit 1',
            )
        else:
            # Each step records that it ran, so the psql stub can answer as a
            # database that the chain has changed.
            _stub(env.venv_dir(version) / "bin" / "python",
                  f'mkdir -p "$STATE" && touch "$STATE/{version}"; exit 0')
        odoo_bin = Path(env.odoo_bin(version))
        odoo_bin.parent.mkdir(parents=True, exist_ok=True)
        odoo_bin.write_text("", encoding="utf-8")
        # The step's own OpenUpgrade code, which the driver requires on disk.
        for directory in _openupgrade_dirs(env, version):
            directory.mkdir(parents=True, exist_ok=True)
    for directory in (env.conf_dir, env.logs_dir, env.checkpoints_dir):
        Path(directory).mkdir(parents=True, exist_ok=True)
    if absorbed:
        old_name, new_name = absorbed
        first, rest = env.chain()[0], env.chain()[1:]
        # The first step declares the merge; no later step mentions the old name,
        # because by then it does not exist to mention.
        for version in env.chain():
            apriori = Path(env.apriori_file(version))
            apriori.parent.mkdir(parents=True, exist_ok=True)
            merged = f'{{"{old_name}": "{new_name}"}}' if version == first else "{}"
            apriori.write_text(
                f"renamed_modules = {{}}\nmerged_modules = {merged}\n", encoding="utf-8"
            )
        # The successor is on disk for every step; the original for none.
        for version in [first, *rest]:
            (Path(env.addons_custom_dir(version)) / new_name).mkdir(parents=True, exist_ok=True)
    (root / "source.dump").write_text("source", encoding="utf-8")
    return script, env


def _openupgrade_dirs(env: MigrationEnv, version: str) -> list[Path]:
    """What the step needs on disk, per OpenUpgrade layout."""
    checkout = Path(env.openupgrade_clone_dir(version))
    if env.uses_legacy_layout(version):
        return [checkout / "addons"]
    return [Path(env.upgrade_scripts_dir(version)), checkout / "openupgrade_framework"]


def _run(root: Path, script: Path, dump: str = "source.dump") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), dump],
        cwd=root,
        capture_output=True,
        text=True,
        env={"PATH": f"{root / 'bin'}:/usr/bin:/bin", "HOME": str(root),
             # Where a step records that it ran, so the psql stub can answer as
             # a database the chain has changed.
             "STATE": str(root / "steps-run")},
    )


def _checkpoints(env: MigrationEnv) -> list[str]:
    return sorted(p.name for p in Path(env.checkpoints_dir).iterdir())


def main() -> int:
    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        print(f"{'ok  ' if condition else 'FAIL'}  {label}")
        if not condition:
            failures.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory(prefix="odwg-driver-") as tmp:
        root = Path(tmp)
        script, env = _build(root)

        first = _run(root, script)
        check("a fresh run migrates the whole chain", first.returncode == 0, first.stderr)
        check("every step is checkpointed",
              _checkpoints(env) == ["00_source.dump", "17.0.dump", "18.0.dump", "source.sha256"],
              str(_checkpoints(env)))

        if not (Path(env.checkpoints_dir) / f"{TARGET}.dump").exists():
            print("\nFAILED: the first run left no checkpoints — the cases below need them.")
            return 1

        # Resume: the last step's checkpoint is gone, the ones before it are not.
        (Path(env.checkpoints_dir) / f"{TARGET}.dump").unlink()
        resumed = _run(root, script)
        check("a re-run resumes from the last checkpoint",
              "[init] restoring checkpoint 17.0" in resumed.stdout
              and "[skip] 17.0 already migrated" in resumed.stdout
              and "[step] upgrading to 18.0" in resumed.stdout,
              resumed.stdout)

        # Gap: an intermediate checkpoint is missing while a later one exists.
        (Path(env.checkpoints_dir) / "17.0.dump").unlink()
        gapped = _run(root, script)
        check("a gap is re-run instead of skipped",
              "[init] restoring checkpoint 00_source" in gapped.stdout
              and "[step] upgrading to 17.0" in gapped.stdout
              and "[step] upgrading to 18.0" in gapped.stdout,
              gapped.stdout)

        # A different source dump must not resume onto these checkpoints.
        (root / "other.dump").write_text("other", encoding="utf-8")
        other = _run(root, script, "other.dump")
        check("checkpoints from another dump are refused",
              other.returncode != 0 and "another source dump" in other.stderr,
              other.stderr)

        # A checkpoint directory with no recorded dump is not one from another
        # dump, and saying so told the operator to delete a chain that may be
        # seven completed steps of a customer's database.
        (env.checkpoints_dir / "source.sha256").unlink()
        legacy = _run(root, script)
        check("checkpoints with no recorded dump are not called another dump's",
              legacy.returncode != 0
              and "do not record which dump they came from" in legacy.stderr
              and "another source dump" not in legacy.stderr,
              legacy.stderr)
        check("and the operator is told how to adopt them",
              "sha256sum" in legacy.stderr and "source.sha256" in legacy.stderr,
              legacy.stderr)
        # Following that instruction must actually resume the chain.
        digest = hashlib.sha256((root / "source.dump").read_bytes()).hexdigest()
        (env.checkpoints_dir / "source.sha256").write_text(digest, encoding="utf-8")
        adopted = _run(root, script)
        check("adopting them resumes instead of restoring from scratch",
              adopted.returncode == 0 and "[init] restoring source dump" not in adopted.stdout,
              adopted.stdout + adopted.stderr)

    with tempfile.TemporaryDirectory(prefix="odwg-driver-") as tmp:
        root = Path(tmp)
        script, env = _build(root, failing_pg_dump=True)
        failed = _run(root, script)
        check("a checkpoint that cannot be written stops the run",
              failed.returncode != 0 and "[fail] checkpoint 00_source" in failed.stderr,
              failed.stdout + failed.stderr)
        check("no step ran after the failed checkpoint",
              "[step] upgrading to" not in failed.stdout and "[done]" not in failed.stdout,
              failed.stdout)
        check("no half-written checkpoint is left behind",
              not any(name.endswith(".tmp") or name.endswith(".dump")
                      for name in _checkpoints(env)),
              str(_checkpoints(env)))

    # A step whose OpenUpgrade code is not on disk must not be checkpointed:
    # Odoo finds no scripts and says nothing, so the driver has to look itself.
    with tempfile.TemporaryDirectory(prefix="odwg-driver-") as tmp:
        root = Path(tmp)
        script, env = _build(root)
        shutil.rmtree(_openupgrade_dirs(env, TARGET)[0])
        missing = _run(root, script)
        check(
            "a missing OpenUpgrade checkout stops the step",
            missing.returncode != 0 and f"[fail] {TARGET}" in missing.stderr,
            missing.stdout + missing.stderr,
        )
        check(
            f"the chain does not claim to be complete without {TARGET}",
            "[done]" not in missing.stdout
            and not (Path(env.checkpoints_dir) / f"{TARGET}.dump").exists(),
            missing.stdout,
        )

    # The legacy (<= 13) layout: its own step command, and its own precondition.
    with tempfile.TemporaryDirectory(prefix="odwg-driver-") as tmp:
        root = Path(tmp)
        script, env = _build(root, source=LEGACY_SOURCE, target=LEGACY_TARGET)
        legacy = _run(root, script)
        check(
            f"a {LEGACY_SOURCE} to {LEGACY_TARGET} chain migrates through the legacy layout",
            legacy.returncode == 0 and "[done]" in legacy.stdout,
            legacy.stdout + legacy.stderr,
        )
    # Fresh state, or the completed checkpoints above would skip the step.
    with tempfile.TemporaryDirectory(prefix="odwg-driver-") as tmp:
        root = Path(tmp)
        script, env = _build(root, source=LEGACY_SOURCE, target=LEGACY_TARGET)
        first_step = env.chain()[0]
        shutil.rmtree(_openupgrade_dirs(env, first_step)[0])
        legacy_missing = _run(root, script)
        # Either signal is correct — coverage sees the empty sources first, the
        # step's own precondition would catch it otherwise. What matters is that
        # the run stops and names the step, instead of migrating nothing.
        stopped = legacy_missing.stdout + legacy_missing.stderr
        check(
            "a missing OpenUpgrade fork stops the legacy step",
            legacy_missing.returncode != 0
            and first_step in stopped
            and "[done]" not in legacy_missing.stdout,
            stopped,
        )

    # A module the chain absorbs mid-way must not be reported as missing at every
    # step after the one that absorbed it. A real 12 -> 14 demo run stopped here:
    # `account_coa_menu` merges into `account_menu` at 13.0, and 14.0's apriori
    # says nothing about the old name, so preflight asked the operator to supply
    # code that should not exist.
    with tempfile.TemporaryDirectory(prefix="odwg-driver-") as tmp:
        root = Path(tmp)
        script, env = _build(root, absorbed=("acme_old_module", "acme_new_module"))
        absorbed_run = _run(root, script)
        check(
            "a module absorbed at the first step does not block the later ones",
            absorbed_run.returncode == 0 and "[done]" in absorbed_run.stdout,
            absorbed_run.stdout + absorbed_run.stderr,
        )
        check(
            "and it is never named as missing",
            "acme_old_module missing" not in absorbed_run.stderr,
            absorbed_run.stderr,
        )

    # A module nobody accounts for must still block, or the carry-forward would
    # have made everything resolve.
    with tempfile.TemporaryDirectory(prefix="odwg-driver-") as tmp:
        root = Path(tmp)
        script, env = _build(root, absorbed=("acme_orphan", "acme_absent"))
        for version in env.chain():
            shutil.rmtree(Path(env.addons_custom_dir(version)) / "acme_absent")
        orphan = _run(root, script)
        check(
            "a module whose successor is nowhere still blocks",
            orphan.returncode != 0 and "acme_orphan missing" in orphan.stderr,
            orphan.stdout + orphan.stderr,
        )

    # A module nobody accounts for blocks — unless the operator recorded what
    # they decided about it. Without this the record was read only by the
    # preflight menu action, so a decision was accepted there and refused here,
    # which left it inert exactly where it mattered. Found on a real 12 -> 19 run
    # stopped by an OCA module never ported to 16.0.
    with tempfile.TemporaryDirectory(prefix="odwg-driver-") as tmp:
        root = Path(tmp)
        script, env = _build(root, absorbed=("acme_orphan", "acme_absent"))
        for version in env.chain():
            shutil.rmtree(Path(env.addons_custom_dir(version)) / "acme_absent")
        # Written the way the tool itself writes it — a wrapper object, not a
        # bare list. A fixture using the other shape passed against a driver
        # that could not read the real file at all.
        Path(env.decisions_file).write_text(
            decisions_to_json([ModuleDecision(
                module="acme_orphan", source=SOURCE, target=TARGET,
                decision="dropped", reason="OCA never ported it",
            )]),
            encoding="utf-8",
        )
        decided = _run(root, script)
        check(
            "a recorded decision lets the run past a module nobody supplies",
            decided.returncode == 0 and "[done]" in decided.stdout,
            decided.stdout + decided.stderr,
        )
        check(
            "and the decision is named, not applied silently",
            "acme_orphan: dropped" in decided.stderr
            and "OCA never ported it" in decided.stderr,
            decided.stderr,
        )

    # A module the chain installs *along the way*. The preflight reads the
    # source database once, so it cannot see one: `partner_firstname_portal`
    # appeared in an OCA repository at 18.0, was auto-installed there, and had
    # vanished from that repository by 19.0 — installed, with no code, and
    # nothing had asked. Each step re-reads the live database for exactly this.
    with tempfile.TemporaryDirectory(prefix="odwg-driver-") as tmp:
        root = Path(tmp)
        script, env = _build(root)
        first, last = env.chain()[0], env.chain()[-1]
        # The stub database grows a module once the first step has run.
        _stub(
            Path(root) / "bin" / "psql",
            f'if [[ "$*" == *base* && "$*" == *latest_version* ]]; then echo {SOURCE}.1.0; '
            'else printf "base\\tOdoo S.A.\\n"; '
            # `if`, not `&&`: a trailing test that fails becomes this stub's exit
            # status, and the host preflight reads that as "PostgreSQL not
            # reachable".
            f'if [ -e "$STATE/{first}" ]; then printf "acme_appeared\\tACME\\n"; fi; fi',
        )
        appeared = _run(root, script)
        check(
            "a module installed after the preflight, resolving nowhere, stops the run",
            appeared.returncode != 0 and "acme_appeared missing" in appeared.stderr,
            appeared.stdout + appeared.stderr,
        )
        check(
            "and it stops at the step that found it, keeping the work before it",
            f"[checkpoint] {first}" in appeared.stdout and "[done]" not in appeared.stdout
            and "since the preflight" in appeared.stderr,
            appeared.stdout + appeared.stderr,
        )
        # Supplying it is enough; nothing else changes.
        for version in env.chain():
            (Path(env.addons_custom_dir(version)) / "acme_appeared").mkdir(
                parents=True, exist_ok=True)
        supplied = _run(root, script)
        check(
            "and supplying it lets the chain finish",
            supplied.returncode == 0 and "[done]" in supplied.stdout,
            supplied.stdout + supplied.stderr,
        )
        assert last  # the chain reached its end

    # A module that resolves but whose manifest names something that does not.
    # Odoo refuses to upgrade it at load time, so coverage saying "everything
    # resolves" was not the same as the step running: a real 12 -> 19 chain
    # failed at step 16 on `account_statement_import_base` needing
    # `account_statement_base`, which lives in another OCA repository.
    with tempfile.TemporaryDirectory(prefix="odwg-driver-") as tmp:
        root = Path(tmp)
        script, env = _build(root, absorbed=("acme_needy", "acme_needy"))
        for version in env.chain():
            module = Path(env.addons_custom_dir(version)) / "acme_needy"
            module.mkdir(parents=True, exist_ok=True)
            (module / "__manifest__.py").write_text(
                "{'name': 'needy', 'depends': ['base', 'never_cloned']}", encoding="utf-8"
            )
            # `base` is present, as it is in any real environment — the Odoo
            # clone provides it. Only the second dependency is missing, so the
            # message names what is actually absent.
            (Path(env.addons_custom_dir(version)) / "base").mkdir(exist_ok=True)
        needy = _run(root, script)
        check(
            "a module whose dependency resolves nowhere stops the run",
            needy.returncode != 0 and "acme_needy needs never_cloned" in needy.stderr,
            needy.stdout + needy.stderr,
        )
        check(
            "and it is stopped before any step runs",
            "[step] upgrading to" not in needy.stdout,
            needy.stdout,
        )
        # Supplying it is enough.
        for version in env.chain():
            (Path(env.addons_custom_dir(version)) / "never_cloned").mkdir(exist_ok=True)
        supplied = _run(root, script)
        check(
            "and supplying the dependency lets the run through",
            supplied.returncode == 0 and "[done]" in supplied.stdout,
            supplied.stdout + supplied.stderr,
        )

    # A decisions file that cannot be read must not let everything through.
    with tempfile.TemporaryDirectory(prefix="odwg-driver-") as tmp:
        root = Path(tmp)
        script, env = _build(root, absorbed=("acme_orphan", "acme_absent"))
        for version in env.chain():
            shutil.rmtree(Path(env.addons_custom_dir(version)) / "acme_absent")
        Path(env.decisions_file).write_text("{not json", encoding="utf-8")
        broken = _run(root, script)
        check(
            "an unreadable decisions file decides nothing",
            broken.returncode != 0 and "acme_orphan missing" in broken.stderr,
            broken.stdout + broken.stderr,
        )

    # A failing step must name itself and its log, not die silently on set -e.
    with tempfile.TemporaryDirectory(prefix="odwg-driver-") as tmp:
        root = Path(tmp)
        script, env = _build(root, failing_step=TARGET)
        failed_step = _run(root, script)
        check(
            "a failing step names itself and its log",
            failed_step.returncode != 0
            and f"step {TARGET} failed" in failed_step.stderr
            and f"{TARGET}.log" in failed_step.stderr,
            failed_step.stdout + failed_step.stderr,
        )

        # The step log the cumulative report and the live view both read. One
        # line per event, appended and never rewritten, so a run killed
        # mid-step still leaves a readable record.
        events = [
            line.split("\t")
            for line in (Path(env.logs_dir) / "steps.tsv").read_text(encoding="utf-8").splitlines()
        ]
        last = events[-1] if events else ["", "", "", "", ""]
        check(
            "a failing step is recorded with the code it failed with",
            [last[2], last[3], last[4]] == [TARGET, "fail", "1"],
            str(events[-3:]),
        )
        check(
            "its start was recorded before it ran",
            [TARGET, "start"] in [[event[2], event[3]] for event in events],
            str(events),
        )
        check(
            "and a run that failed writes no run-ok",
            not any(event[3] == "run-ok" for event in events),
            str(events),
        )
        check(
            "every line carries a timestamp journalctl can take",
            all(
                re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d", event[0])
                for event in events
            ),
            str([event[0] for event in events]),
        )

    # --- neutralisation: every database the driver leaves behind, and every start ---
    with tempfile.TemporaryDirectory(prefix="odwg-neutral-driver-") as tmp:
        root = Path(tmp)
        script, env = _build(root)
        missing = _run(root, script)
        check("without neutralise.sql the driver says the database is NOT neutralised",
              missing.returncode == 0 and "is NOT neutralised" in missing.stderr,
              missing.stderr[-400:])

    with tempfile.TemporaryDirectory(prefix="odwg-neutral-driver-") as tmp:
        root = Path(tmp)
        script, env = _build(root)
        for name, text in ((templates.NEUTRALISE_FILE, templates.render_neutralise_sql()),
                           (templates.NEUTRAL_CHECK_FILE, templates.render_neutral_check_sql())):
            (env.root / name).write_text(text, encoding="utf-8")
        # Every -f the driver hands psql is logged, in order; the check can be made
        # to fail, as it does on a database something can still act from.
        log = root / "psql-files.log"
        _stub(root / "bin" / "psql",
              f'for a in "$@"; do case "$a" in *.sql) echo "$(basename "$a")" >> {log};; '
              'esac; done; '
              'if [[ "$*" == *neutralise_check.sql* && -n "${FAIL_CHECK:-}" ]]; then '
              'echo "can still act on the outside: crons (3)" >&2; exit 1; fi; '
              'if [[ "$*" == *base* && "$*" == *latest_version* ]]; then '
              f'echo {SOURCE}.1.0; else printf "base\\tOdoo S.A.\\n"; fi')
        run = _run(root, script)
        calls = log.read_text().split() if log.exists() else []
        expected = [templates.NEUTRALISE_FILE, templates.NEUTRAL_CHECK_FILE] * (1 + len(env.chain()))
        check("the driver neutralises and checks after the source and after every step",
              run.returncode == 0 and calls == expected, f"{calls}\n{run.stderr[-300:]}")
        events = [line.split("\t") for line in Path(env.steps_file).read_text().splitlines()]
        check("each neutralisation is in the step log, as no step of its own",
              [e[4] for e in events if e[3] == "neutralised"] == ["00_source", *env.chain()]
              and all(e[2] == "-" for e in events if e[3] == "neutralised"), str(events))
        generated = "\n".join([templates.render_run_migration_sh(env),
                                templates.render_neutralise_sql(),
                                templates.render_neutral_check_sql(),
                                templates.render_open_for_testing_sh(env)])
        check("nothing the environment runs can give production's settings back",
              "no neutralisation is recorded" not in generated
              and "jsonb_populate_record(NULL::%I" not in generated)

        for path in Path(env.checkpoints_dir).iterdir():
            path.unlink()
        log.unlink()
        refused = subprocess.run(
            ["bash", str(script), "source.dump"], cwd=root, capture_output=True, text=True,
            env={"PATH": f"{root / 'bin'}:/usr/bin:/bin", "HOME": str(root),
                 "STATE": str(root / "steps-run"), "FAIL_CHECK": "1"})
        check("a database that stays armed stops the run before its checkpoint",
              refused.returncode != 0 and "can still act on the outside" in refused.stderr
              and not (Path(env.checkpoints_dir) / "00_source.dump").exists(),
              refused.stderr[-300:])

        # The start script: re-neutralise, check, then Odoo with no cron thread.
        opener = root / "open_for_testing.sh"
        opener.write_text(templates.render_open_for_testing_sh(env), encoding="utf-8")
        started = root / "odoo-started.log"
        _stub(env.venv_dir(TARGET) / "bin" / "python", f'echo "$*" > {started}')
        Path(env.config_file(TARGET)).write_text("[options]\n", encoding="utf-8")

        def open_(*args: str, fail: bool = False) -> subprocess.CompletedProcess[str]:
            extra = {"FAIL_CHECK": "1"} if fail else {}
            return subprocess.run(["bash", str(opener), *args], cwd=root, capture_output=True,
                                  text=True, env={"PATH": f"{root / 'bin'}:/usr/bin:/bin",
                                                  "HOME": str(root), **extra})

        armed = open_(TARGET, "acme_copy", fail=True)
        check("open_for_testing refuses a database that can still act, and starts nothing",
              armed.returncode != 0 and "not starting" in armed.stderr and not started.exists(),
              armed.stderr[-300:])
        ok = open_(TARGET, "acme_copy")
        argv = started.read_text() if started.exists() else ""
        check("open_for_testing starts Odoo with no cron thread, on loopback, for that database",
              ok.returncode == 0 and "--max-cron-threads=0" in argv
              and "--http-interface=127.0.0.1" in argv and "-d acme_copy" in argv,
              f"{argv}\n{ok.stderr[-300:]}")
        check("open_for_testing refuses a version outside the chain and a bad database name",
              open_("11.0", "acme_copy").returncode != 0
              and open_(TARGET, "x;rm -rf /").returncode != 0)

        # With an intake: the client's source, the reference refused, a copy's filestore.
        from odoo_dwg.intake import Core, IntakeRecord
        env.intake = IntakeRecord("ACME_original", "acme_reader", "client-src/acme", ("custom",),
                                  Core("ocb", "4" * 40))
        opener.write_text(templates.render_open_for_testing_sh(env), encoding="utf-8")
        source_bin = Path(env.source_odoo_bin)
        source_bin.parent.mkdir(parents=True, exist_ok=True)
        source_bin.write_text("", encoding="utf-8")
        _stub(env.venv_dir(SOURCE) / "bin" / "python", f'echo "$*" > {started}')
        Path(env.config_file(SOURCE)).write_text("[options]\n", encoding="utf-8")
        started.unlink(missing_ok=True)
        refused_ref = open_(SOURCE, "ACME_original")
        check("open_for_testing refuses the reference, which nothing modifies",
              refused_ref.returncode != 0 and "reference" in refused_ref.stderr
              and not started.exists(), refused_ref.stderr[-200:])
        store = env.data_dir / "filestore" / "ACME_original" / "ab"
        store.mkdir(parents=True)
        (store / "abcd").write_text("attachment\n", encoding="utf-8")
        opened = open_(SOURCE, "acme_copy")
        argv = started.read_text() if started.exists() else ""
        copy = env.data_dir / "filestore" / "acme_copy"
        check("the source starts from the client's pinned core, with the environment's data dir",
              opened.returncode == 0 and str(source_bin) in (opener.read_text())
              and f"--data-dir={env.data_dir}" in argv and "--max-cron-threads=0" in argv,
              f"{argv}\n{opened.stderr[-300:]}")
        same_inode = (copy / "ab" / "abcd").exists() and \
            (copy / "ab" / "abcd").stat().st_ino == (store / "abcd").stat().st_ino
        (copy / "ab" / "new-in-the-copy").write_text("x", encoding="utf-8")
        check("a copy gets the reference's filestore by hard links, and its new files stay its own",
              same_inode and not (store / "new-in-the-copy").exists())

    if failures:
        print("\n".join(["", "FAILED:"] + failures))
        return 1
    print("\nThe generated driver behaves as documented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
