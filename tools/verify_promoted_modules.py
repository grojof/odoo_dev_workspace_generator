#!/usr/bin/env python3
"""Execute the promote → consume cycle a rehearsed migration depends on.

A migration is rehearsed several times and run once. The rehearsals produce the
corrections; the final run must *apply* them rather than derive them a second
time. The unit suite asserts the plans' text — it may not shell out (CLAUDE.md)
— so it can say the commands look right and not that the cycle works.

This runs the real plans, with a stub module migrator standing in for
`odoo-module-migrate`, and asserts the thing the operator actually cares about:

- the first staging derives every step, and the migrator runs once per step;
- a correction made by hand survives promotion;
- the second staging derives **nothing** and lands exactly the reviewed code;
- the throwaway git repository the migrator needs does not travel with it;
- divergence is seen once work continues in the environment after promotion.

    python tools/verify_promoted_modules.py

Needs `bash` and `git`. No network, no PostgreSQL, no root, nothing written
outside a temporary directory.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odoo_dwg import planners, preflight  # noqa: E402
from odoo_dwg.models import MigrationEnv, PromotedModules  # noqa: E402

MODULE = "client_sales"
SOURCE, TARGET = "12.0", "14.0"


def _run(commands, cwd: Path) -> None:
    """Apply a plan the way ``system.apply_commands`` does: stop at the first
    step that fails, so a broken command cannot be mistaken for a passing case."""
    for item in commands:
        result = subprocess.run(
            ["bash", "-c", item.command], cwd=cwd, capture_output=True, text=True
        )
        if result.returncode != 0:
            raise SystemExit(
                f"step failed: {item.description}\n{item.command}\n{result.stderr.strip()}"
            )


def _stub_migrator(env: MigrationEnv, calls: Path) -> None:
    """A migrator that records every invocation and marks what it touched.

    The real one rewrites the module for the version bump; all this needs to do
    is be distinguishable from *not having run*.
    """
    binary = env.staging_tool_venv / "bin" / "odoo-module-migrate"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text(
        "#!/bin/bash\n"
        f'echo "$@" >> {calls}\n'
        '# --directory <dir> --modules <name> --init-version-name <v> '
        '--target-version-name <v>\n'
        'while [ $# -gt 0 ]; do\n'
        '  case $1 in --directory) dir=$2 ;; --modules) mod=$2 ;; '
        '--target-version-name) to=$2 ;; esac\n'
        '  shift\n'
        'done\n'
        'echo "# migrated to $to" >> "$dir/$mod/models.py"\n',
        encoding="utf-8",
    )
    binary.chmod(0o755)


def _calls(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0


def main() -> int:
    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        print(f"{'ok  ' if condition else 'FAIL'}  {label}")
        if not condition:
            failures.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory(prefix="odwg-promote-") as tmp:
        root = Path(tmp)
        MigrationEnv.base_dir = str(root / "envs")
        env = MigrationEnv(source=SOURCE, target=TARGET)
        kept = PromotedModules(base_dir=str(root / "kept"))
        kept.validate()

        source_dir = root / "src"
        (source_dir / MODULE).mkdir(parents=True)
        (source_dir / MODULE / "models.py").write_text("# the client's code\n", encoding="utf-8")
        calls = root / "migrator-calls"
        _stub_migrator(env, calls)

        steps = list(env.chain())

        # --- the rehearsal: everything is derived --------------------------
        _run(
            planners.plan_stage_module(
                env, MODULE, source_dir, promoted=kept, exists=Path.exists
            ),
            root,
        )
        check(
            "the first staging derives every step",
            _calls(calls) == len(steps),
            f"{_calls(calls)} migrator calls for {len(steps)} steps",
        )

        # --- the operator reviews, by hand, as they would ------------------
        # Every step, not just the first: a correction made to 13.0 after 14.0 was
        # already derived does not reach 14.0, which is the chain working as it
        # should — each version's reviewed code is that version's.
        for version in steps:
            reviewed = env.addons_custom_dir(version) / MODULE / "models.py"
            reviewed.write_text(
                reviewed.read_text(encoding="utf-8") + f"# reviewed by hand for {version}\n",
                encoding="utf-8",
            )

        _run(planners.plan_promote_module(env, MODULE, steps, kept), root)
        check(
            "a correction made by hand survives promotion, per version",
            all(
                f"reviewed by hand for {version}"
                in (kept.module_dir(version, MODULE) / "models.py").read_text(encoding="utf-8")
                for version in steps
            ),
            str(kept.version_dir(steps[0])),
        )
        check(
            "the throwaway git repository does not travel with it",
            not (kept.module_dir(steps[0], MODULE) / ".git").exists(),
            "a .git came along",
        )
        check(
            "the environment is still there after promoting",
            (env.addons_custom_dir(steps[0]) / MODULE).is_dir(),
            "promotion moved instead of copying",
        )

        # --- the final run: nothing is derived -----------------------------
        calls.unlink()
        for version in steps:
            # A fresh environment, as a new dump would give: the staged code is
            # gone and only the promoted copy remains.
            target = env.addons_custom_dir(version) / MODULE
            subprocess.run(["rm", "-rf", str(target)], check=True)
        _run(
            planners.plan_stage_module(
                env, MODULE, source_dir, promoted=kept, exists=Path.exists
            ),
            root,
        )
        check(
            "the final run derives nothing",
            _calls(calls) == 0,
            f"{_calls(calls)} migrator calls where none were expected",
        )
        landed = (env.addons_custom_dir(steps[-1]) / MODULE / "models.py").read_text(encoding="utf-8")
        check(
            "and lands exactly the reviewed code, for the version that ships",
            f"reviewed by hand for {steps[-1]}" in landed,
            landed,
        )

        # --- divergence, once work continues -------------------------------
        check(
            "the two copies agree right after a staging that consumed them",
            all(state == "same" for _v, state in preflight.divergence(env, MODULE, kept, steps)),
            str(preflight.divergence(env, MODULE, kept, steps)),
        )
        again = env.addons_custom_dir(steps[0]) / MODULE / "models.py"
        again.write_text(again.read_text(encoding="utf-8") + "# still working\n", encoding="utf-8")
        states = dict(preflight.divergence(env, MODULE, kept, steps))
        check(
            "and diverge as soon as the environment is edited again",
            states.get(steps[0]) == "diverged" and states.get(steps[-1]) == "same",
            str(states),
        )

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("\nThe promote / consume cycle behaves as documented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
