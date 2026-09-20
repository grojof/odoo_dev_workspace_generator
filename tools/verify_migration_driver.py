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
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odoo_dwg import templates  # noqa: E402
from odoo_dwg.models import MigrationEnv  # noqa: E402

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
) -> tuple[Path, MigrationEnv]:
    """Render the driver and the stub host it runs against."""
    MigrationEnv.base_dir = str(root / "envs")
    env = MigrationEnv(source=source, target=target)
    script = root / "run_migration.sh"
    script.write_text(templates.render_run_migration_sh(env), encoding="utf-8")

    stubs = root / "bin"
    # One installed module authored by Odoo: coverage warns, never blocks.
    _stub(stubs / "psql",
          f'if [[ "$*" == *base* && "$*" == *latest_version* ]]; then echo {source}.1.0; '
          'else printf "base\\tOdoo S.A.\\n"; fi')
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
            _stub(env.venv_dir(version) / "bin" / "python", "exit 0")
        odoo_bin = Path(env.odoo_bin(version))
        odoo_bin.parent.mkdir(parents=True, exist_ok=True)
        odoo_bin.write_text("", encoding="utf-8")
        # The step's own OpenUpgrade code, which the driver requires on disk.
        for directory in _openupgrade_dirs(env, version):
            directory.mkdir(parents=True, exist_ok=True)
    for directory in (env.conf_dir, env.logs_dir, env.checkpoints_dir):
        Path(directory).mkdir(parents=True, exist_ok=True)
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
        env={"PATH": f"{root / 'bin'}:/usr/bin:/bin", "HOME": str(root)},
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

    if failures:
        print("\n".join(["", "FAILED:"] + failures))
        return 1
    print("\nThe generated driver behaves as documented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
