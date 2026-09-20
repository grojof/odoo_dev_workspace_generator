# Answer without the menu

## Why

Every question the tool can answer is behind an interactive menu. `odoo-dwg migrate` takes no arguments; it
opens a menu and waits. That is right for anything that changes the host — plan → preview → confirm → apply
is inviolable — but it also means the **read-only** answers cannot be had any other way: not from a script,
not from a pipe, not from a second terminal during a run, and not by an assistant asked to look.

The three thin helpers this phase still owes — migration triage, an OpenSnitch rule check, a Mailpit
configuration check — all want the same thing, and none of them wants to write anything. Without a
non-interactive way to *read*, each would have to re-implement the parsing that `runlog.py`, `tester.py`
and `egress.py` already do, and the copy would drift from the original the first time either changed.

There is also a question the tool cannot answer at all yet. OpenSnitch evaluates rules in file-name order
and the first match decides — `egress.py` says so, and names its rules `00-odwg-` for exactly that reason —
but nothing checks whether the rules on the host still say what the tool wrote, or whether something now
sorts ahead of them. A rule that pre-empts the Odoo rule is invisible until a migration reaches the
internet.

## What changes

- **`audit_rules`** (new, pure, in `egress.py`): the tool's own rules as they are on disk, against what it
  would write. It reports a rule of ours that is missing, changed, or disabled, a file that is not JSON,
  and — the one that matters — **a foreign rule that sorts before ours**, which is the only way the Odoo
  rule can be pre-empted.
- **A read-only subcommand surface**, which writes nothing and needs no terminal:
  - `odoo-dwg egress check` — the rule audit above.
  - `odoo-dwg mail check --database X` — the mail verdict the menu already prints.
  - `odoo-dwg migrate report --source A --target B` — the cumulative run report.
  - `odoo-dwg migrate probes --source A --target B --database X` — the tester's verdicts.
  Each exits non-zero when it has something to report, so it is usable in a script as well as by eye.
- **Three skills** in `.claude/skills/`, thin over those four commands: they run them, read the docs page
  the finding points at, and say what to do. No skill parses a log, a rule file or a database itself — the
  deterministic work stays in the tool, which is where it is tested.

Anything that changes the host stays in the menu behind its phrase. The skills say which menu action to
use; they do not perform it.

## Impact

- Affected specs: `operator-interface`, `egress-control`
- Affected code: `odoo_dwg/egress.py`, `odoo_dwg/cli.py`, `odoo_dwg/system.py`, `odoo_dwg/i18n.py`
- New: `.claude/skills/{migration-triage,opensnitch-rule-check,mailpit-config}/SKILL.md`
- Docs: `docs/commands.md`, `docs/egress-control.md`, `README.md`, `CHANGELOG.md`, `docs/roadmap.md`
