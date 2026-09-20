#!/usr/bin/env python3
"""Run ShellCheck over every shell script the tool generates.

The scripts are rendered from Python, so an editor never lints them and the unit
suite can only assert their text. This renders each one — for several Odoo
versions and both OpenUpgrade layouts — into a temporary directory and runs
`shellcheck` on it.

    python tools/verify_generated_shell.py          # default severity (style and up)
    python tools/verify_generated_shell.py --severity warning

ShellCheck is a development tool, not a dependency of the package: install it
with `uv tool install shellcheck-py`, `pipx install shellcheck-py`, or
`apt install shellcheck`. It has limits — it does not catch a failure masked by
`;` in a function whose last command succeeds, which is what
`tools/verify_migration_driver.py` exists for — so the two are complementary.

No network, no PostgreSQL, nothing written outside its temp directory.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odoo_dwg import planners, templates  # noqa: E402
from odoo_dwg.models import MigrationEnv, WorkspaceConfig, resolve_interpreter  # noqa: E402

# Both OpenUpgrade layouts (<= 13 fork, >= 14 upgrade-path) and both interpreter
# sources (uv-provided, host), so no rendering branch goes unchecked.
WORKSPACE_VERSIONS = ["12.0", "13.0", "16.0", "18.0", "19.0"]
CHAINS = [("12.0", "19.0"), ("16.0", "18.0")]


def _render(into: Path) -> list[Path]:
    written: list[Path] = []

    def write(name: str, text: str) -> None:
        path = into / name
        path.write_text(text, encoding="utf-8")
        written.append(path)

    cfg = WorkspaceConfig(name="acme", versions=WORKSPACE_VERSIONS, oca_repos=["web", "server-tools"])
    interpreters = {v: resolve_interpreter(v, host_python="3.12") for v in cfg.versions}
    write("setup_venv.sh", templates.render_setup_venv_sh(cfg, interpreters))
    for version in cfg.versions:
        write(f"run-odoo{version.split('.')[0]}.sh", templates.render_run_sh(cfg, version))
    for source, target in CHAINS:
        env = MigrationEnv(source=source, target=target)
        write(
            f"run_migration_{source.split('.')[0]}_{target.split('.')[0]}.sh",
            templates.render_run_migration_sh(env),
        )
        write(
            f"seed_demo_{source.split('.')[0]}.sh",
            templates.render_seed_demo_sh(env, ["partner_firstname", "web_responsive"]),
        )
    # The `pg_hba` steps are not files, but they are the longest shell this project
    # writes and they run under `sh` (``system.run`` uses ``shell=True``), so they
    # are linted as that shell rather than as bash.
    for index, command in enumerate(planners.plan_pg_hba_trust("odoo"), start=1):
        if "\n" in command.command:
            write(f"pg_hba_step_{index}.sh", f"#!/bin/sh\n{command.command}\n")
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--severity", default="style", choices=["error", "warning", "info", "style"],
        help="lowest severity to report (default: style, i.e. everything)",
    )
    args = parser.parse_args()

    shellcheck = shutil.which("shellcheck")
    if not shellcheck:
        print(
            "shellcheck not found. Install it with one of:\n"
            "  uv tool install shellcheck-py\n"
            "  pipx install shellcheck-py\n"
            "  sudo apt install shellcheck",
            file=sys.stderr,
        )
        return 2

    with tempfile.TemporaryDirectory(prefix="odwg-shell-") as tmp:
        scripts = _render(Path(tmp))
        print(f"Checking {len(scripts)} generated scripts with {shellcheck}")
        result = subprocess.run(
            [shellcheck, "--severity", args.severity, *(str(p) for p in scripts)],
            capture_output=True,
            text=True,
        )
        # Paths in the findings are temporary; name the renderer instead.
        output = result.stdout.replace(tmp + "/", "")
        if result.returncode != 0:
            print(output or result.stderr)
            print("\nFix the renderer in odoo_dwg/templates.py or odoo_dwg/planners.py, not the rendered file.")
            return 1

    print("Every generated script is clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
