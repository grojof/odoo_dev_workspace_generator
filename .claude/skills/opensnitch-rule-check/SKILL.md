---
name: opensnitch-rule-check
description: Check whether the host's OpenSnitch rules still say what odoo_dwg wrote, and whether anything now sorts ahead of them. Use when asked to verify the outbound firewall rules, or before a migration that must not reach the internet.
license: LGPL-3.0
compatibility: Requires odoo-dwg on PATH (or `python -m odoo_dwg`) and OpenSnitch installed on the host.
metadata:
  author: odoo_dwg
  version: "1.0"
---

Run the check. Do not read the rule files yourself and do not compare them by eye — the comparison is the
tool's, and it is tested there.

```bash
odoo-dwg egress check --lang en
```

The exit code is the verdict: **0** nothing to report, **1** it found something, **2** it could not tell
(usually: OpenSnitch is not installed, or `/etc/opensnitchd/rules` is not readable by you).

## Reading what it prints

| Finding | What it means | What to say |
|---|---|---|
| `sorts first` | A rule that is **not** the tool's is evaluated before the tool's rules. OpenSnitch takes the first match, so this rule can let Odoo out. | The one worth acting on. Show the file name and ask whether that rule is deliberate. |
| `absent` | A rule the tool would write is not on the host. | Menu → Provision → *Outbound firewall and mail capture* rewrites the tool's own rules. |
| `disabled` | One of the tool's rules has `enabled: false`. | Same. Note that a disabled rule confines nothing. |
| `changed` | One of the tool's rules differs from what the tool would write. Formatting alone is **not** reported — this is a difference in what OpenSnitch would do. | Ask whether the edit was deliberate before offering to rewrite it. |
| `unreadable` | A file in the rules directory is not JSON, so what OpenSnitch does with it cannot be predicted. | Show the file name. |

## Rules

- **Change nothing.** This check writes nothing, and neither do you. A rule the operator wrote deliberately
  to sort first is a legitimate thing to have, and only they know which it is. Name the menu action; do not
  run it.
- **Exit 2 is not "clean".** If the tool could not read the rules, say so. Never report a firewall as
  correct because a check failed to run.
- Background on why the prefix is `00-odwg-` and why file-name order decides: `docs/egress-control.md`.
