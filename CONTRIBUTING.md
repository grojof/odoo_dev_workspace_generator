# Contributing

Thanks for your interest. This project is small and spec-driven; the bar is consistency.

## Ground rules

- **Zero runtime dependencies** — Python 3.12+ standard library only. Adding a runtime dependency is an
  architectural decision, not a convenience.
- **Spec-first for non-trivial changes**: behaviour lives in `openspec/specs/`; a change is a directory
  under `openspec/changes/<name>/` holding `proposal.md` (why and what), `design.md` (the decisions worth
  recording), `tasks.md` (the checklist) and `specs/<capability>/spec.md` (the delta). Implement, keep
  `openspec validate --specs` green, then move the directory to `openspec/changes/archive/<date>-<name>/`
  and fold its delta into the capability's spec. Trivial fixes may go straight to a PR. The archive is also
  where to look for *why* something is the way it is.
- **Plan → preview → apply is inviolable**: planners stay pure (building a command is not running it), and
  nothing mutates the host without a previewed, confirmed plan.
- Every Odoo/OpenUpgrade fact must be anchored to official documentation (see `docs/`).
- AI agents working on this repository follow [`AGENTS.md`](AGENTS.md).

## Set up

The package itself has no dependencies; the checks below do.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"             # pytest, ruff
npm install -g @fission-ai/openspec@latest   # the `openspec` CLI (Node)
```

[`docs/host/wsl-setup.md`](docs/host/wsl-setup.md) covers getting a host ready from nothing.

## Checks before a PR

```bash
python -m pytest -q                 # unit tests (no network, no real filesystem side effects)
python -m ruff check .              # lint
openspec validate --specs           # capability specs well-formed
python -m odoo_dwg --help           # CLI smoke test
```

Real end-to-end validation happens on a Linux host (WSL Ubuntu 24.04 is the reference box).

**A stub must be able to disagree with the code it stands in for.** Two bugs reached a real host past a
green verifier because its fixture was built from the product's own accessor, or failed in a way the real
thing never fails:

- the demo seed's precondition was checked against a file the verifier had created at
  `env.odoo_bin(source)` — the same wrong path the product used — so the stub agreed with the mistake;
- "a failed `pg_dump` leaves nothing behind" passed against a script that *did* leave the partial file,
  because the stub exited non-zero without writing one.

When writing a stub, derive its paths from what the real host would have, not from the code under test, and
make it fail the way the real binary fails — after doing part of the work, and refusing what the real one
refuses (a `psql` with no `-U` must die, or a check missing its connection arguments passes here and does
nothing there).

The checks above need no network and change nothing. The tools below are **not** part of the suite. Each
checks something the suite cannot: an external fact that may have moved (the support matrix, the editor
configuration, the pinned firewall and mail-capture releases), or the behaviour of generated shell on a real
host (the migration driver, every generated script, the `pg_hba.conf` rewriter). Run the first kind when the
fact may have changed, the second when you touch what renders it, and all of them before a release:

```bash
python tools/verify_support_matrix.py            # re-derive every bound from its official source
python tools/verify_support_matrix.py 18.0 19.0  # only these versions
python tools/verify_odools_config.py             # the editor config vs the latest OdooLS release
python tools/verify_workspace_versions.py        # build every version's venv, start Odoo on each
python tools/verify_egress_pins.py               # OpenSnitch/Mailpit pins vs their signed/published sources
python tools/verify_migration_driver.py          # run the generated migration driver against stub binaries
python tools/verify_generated_shell.py           # ShellCheck every generated script
python tools/verify_pg_hba_trust.py              # run the pg_hba rewriter, and ask PostgreSQL about it
python tools/verify_promoted_modules.py         # promote reviewed code, then stage again and derive nothing
python tools/verify_mail_capture.py              # capture, check and restore a database's mail configuration
python tools/verify_migration_tester.py          # generate the rehearsal tester, and run the query it asks
python tools/verify_demo_seed.py                 # run the generated demo seed against stub binaries
python tools/verify_neutralisation.py            # neutralise, check, re-apply and restore on a throwaway PostgreSQL
python tools/verify_neutralise_sources.py        # the catalogue vs Odoo's neutralize.sql files and the OCA sources it cites
python tools/verify_intake.py                    # intake on real tools: restore, reader role, core, filestore, audits, bank lines, journal codes
python tools/verify_migration_audit.py           # migrate audit on 12.0- and 18.0-shaped databases, and a role refused one table
python tools/verify_grouped_invoice_lines.py     # the repair of grouped invoice items, on a throwaway PostgreSQL
python tools/verify_source_taxes.py              # keep the source's journal-item taxes, take back OpenUpgrade 13.0's additions
python tools/verify_filed_declarations.py        # keep a source's filed declarations, put back what the chain deletes
python tools/verify_retired_modules.py           # retire modules before the chain: the driver's stage on a throwaway PostgreSQL
python tools/verify_migrated_payments.py         # the payments repair's duplicates and journals, on a throwaway PostgreSQL
```

| Tool | Needs |
|---|---|
| `verify_support_matrix.py`, `verify_odools_config.py`, `verify_egress_pins.py` | the network |
| `verify_workspace_versions.py` | the network **and** a host it may change (it previews, asks, and cleans up) |
| `verify_generated_shell.py` | `shellcheck` on the host |
| `verify_pg_hba_trust.py`, `verify_mail_capture.py`, `verify_migration_tester.py`, `verify_neutralisation.py`, `verify_migration_audit.py`, `verify_grouped_invoice_lines.py`, `verify_source_taxes.py`, `verify_filed_declarations.py`, `verify_retired_modules.py`, `verify_migrated_payments.py`, `verify_intake.py` (also `git` and `tar`) | the host's PostgreSQL binaries; each runs a cluster of its own |
| `verify_neutralise_sources.py` | the local clones under `~/odoo-migrations/.repos` (`git` may fetch an OCA file it cites) |
| `verify_migration_driver.py`, `verify_demo_seed.py` | nothing but `bash` |
| `verify_promoted_modules.py` | nothing but `bash` and `git` |

`verify_demo_seed.py` executes the generated `seed_demo.sh` against stub `createdb`/`psql`/`pg_dump` and
a stub Odoo interpreter: a fresh seed produces a dump in the format the driver takes and installs `base`
first, each chosen module is installed in its own call, a module that will not install is named and no dump
is produced without it, an existing dump or database is refused rather than replaced, and a `pg_dump` that
fails leaves neither a dump nor a half-written one. That last case passed against a script that *did* leave
the partial file, until the stub was made to fail the way a real `pg_dump` fails — after writing something.

`verify_migration_audit.py` runs `migrate audit` through the CLI against a cluster of its own. On a
12.0-shaped copy it must find a shared journal code (and a case-only one as information), a bank day
imported twice, a line matching a payment on the bank and a closed-period line. On an 18.0-shaped database
it must find the missing unique constraint and not the truncated one, the foreign key or an uninstalled
module's; the empty required fields, with the archived-only one as information and a transient model not
read; and the one statement line stored as reconciled with a suspense line. Read by a role refused one
table, that check must be unreadable and the others must stand.

`verify_grouped_invoice_lines.py` runs the repair of grouped invoice items, as the driver hands it to
`psql`, on invoices shaped the way OpenUpgrade 13.0 leaves them and 16.0 types them. It covers:
- a grouped customer invoice, with a cent of rounding, a partner to take and an analytic line, a
  declaration link and an EC sales list detail to move;
- a vendor bill whose lines cancel out under two taxes, and a vendor refund;
- a line given the union of its group's taxes;
- a move with one group that adds up and one that does not;
- an open grouped item on a reconcilable account, whose lines stay open;
- a foreign-currency invoice, a reconciled grouped item and one a reconciliation points at, each left
  with its reason;
- a journal entry never touched;
- a second run that repairs nothing, and a check made to fail, which must keep nothing;
- databases without grouped items or without OpenUpgrade 13.0's columns.

It found that a two-column detail table (its `id` and the line) was being copied as a many-to-many link.

`verify_source_taxes.py` keeps a 12.0-shaped source's journal-item taxes, simulates what OpenUpgrade 13.0
leaves, and takes the additions back. It covers:
- an item grouped in the source that gained its invoice line's other tax;
- a payable line given its invoice line's tax;
- an item that gained a tax its invoice line did not bear, which must stay;
- tax-group children the new model drops, which must not come back;
- an inserted item, never touched;
- the list and the dropped tables;
- a database without the kept taxes (skipped, unchanged) and a source without the relation.

`verify_filed_declarations.py` keeps a source's filed declarations, then simulates a later module version
that stops shipping the older map: the update deletes its lines, and the cascade takes a return's boxes and
links. It also removes a journal item and makes a text column translatable. Every box must come back with
its id and amount, with its map line, map and links, except the link to the journal item that is gone. A box
changed by hand must stop it and keep nothing. Without the copies it skips, and a source without
declarations keeps nothing.

`verify_retired_modules.py` runs the driver's own `retire_before_chain` against a 12.0-shaped registry on
a throwaway PostgreSQL. Only the source's Odoo is a stub, making an uninstall's changes in SQL. It covers:
- exact row counts with no ANALYZE, and a column's values that ignore `false` and `''`;
- the registry, a wizard, the module's own group, an empty column and a stored related one, none of them
  data;
- a table's rows, a membership the group's removal cascaded to, and a filled column: data lost, which
  stops the stage;
- the same losses accepted by name, which pass with their reasons listed;
- an installed dependent not retired, which stops the stage before Odoo runs.

`verify_migrated_payments.py` runs the payments repair's SQL on an 18.0-shaped database. It covers:
- a duplicate on a manual entry, removed with its own links;
- duplicates kept because a journal item points at them, because they have a payment line their twin
  lacks, or because they have a message;
- two payments on the order's own entry, both kept;
- a payment given its order's bank journal and method line, its entry untouched;
- a general journal, or two fitting method lines, which give no journal;
- a second run that changes nothing, and a database without payment orders.

Odoo's recompute of states runs in the target's Odoo, so it is checked on a real migrated database.

`verify_migration_tester.py` generates the rehearsal tester from analysis lines copied verbatim out of
OpenUpgrade's files, then asks whether the result is a *module*: every `.py` compiles, the manifest
evaluates to a dict that ships what it declares and sets no `auto_install`, the data file parses with one
record per probe and unique ids, and the access rule is read-only on its own model. It then creates
`ir_model`, `ir_model_fields` and the probe table in a throwaway cluster and runs the real query, so both
findings are produced by PostgreSQL rather than asserted. It also checks that no status in the whole
harvested vocabulary is claimed by two class patterns, and — where the host has the environment's clones —
generates the real chain's tester and checks every probe against a record that states it.

`verify_mail_capture.py` runs capture → check → restore against a cluster of its own, on two
`ir_mail_server` schemas that differ the way Odoo's differ across the chain (a 12-era one, and a 19-era one
where `smtp_authentication` is `NOT NULL`). It asserts what the operator depends on: the client's row comes
back from restore column for column, a server the client had switched off is not switched on, a second
capture leaves the capture's own server active, restore leaves no table behind, and a database that was
never captured is refused. The unit suite asserts the SQL's text; this runs it — which is how a capture
that switched off its own server on the second run, and a boolean read as `t` when PostgreSQL renders it
`true`, were both found.

`verify_promoted_modules.py` runs the promote → consume cycle a rehearsed migration depends on, with a
stub module migrator: the first staging derives every step, a correction made by hand survives
promotion, the second derives **nothing** and lands exactly the reviewed code, the throwaway git
repository does not travel with it, and divergence appears as soon as work continues in the
environment. The unit suite can only assert the plans' text; this executes them.

`verify_migration_driver.py` renders `run_migration.sh` into a temporary directory and executes it with stub `psql`/`pg_dump`/`pg_restore`/`uv`, covering the fresh run,
resume, a gap in the checkpoints, a dump that does not match, a checkpoint that cannot be written, a step
whose OpenUpgrade code is not on disk, a step that fails — which must name itself and its log — and a
12 → 14 chain, so the ≤ 13 layout's own step command and preconditions are executed too, not only the
upgrade-path ones, and the check and repair after the 14.0 step are recorded before its checkpoint. A 14.0 checkout without OCA/OpenUpgrade#6005 must stop before the step, and statement lines still stored as reconciled after it must stop it before its checkpoint. The retirement before the chain is run too: an unaccepted loss stops before the source checkpoint, an accepted one is listed with its reason, a resumed run does not retire again, and a dependent not retired stops it before any change. The unit suite may not shell out, so this is where the *behaviour* of the generated shell is checked — run it
whenever `render_run_migration_sh` changes.

`verify_pg_hba_trust.py` runs the `pg_hba.conf` rewriter over every shape of that file this project has been
caught by, the server's verification step over more, and the check's own answer against whether
`postgres` really connects. The shapes it must narrow: a blanket trust
written as CIDR, as `localhost`/`samehost`, indented, in `address netmask` form, as `hostnossl`, `hostssl` or
`hostgssenc`, on `all`, on `0.0.0.0/0`, on `127.0.0.0/8`, on one database, and with a quoted address. The
shapes it must leave alone: the Ubuntu default, a file with no `host` rules, one this tool already narrowed,
and a password rule whose comment merely mentions trust — a role literally named `all` is covered where
it matters, in the verification step's own cases. And the shapes where
it must insert the role's line rather than read one as reached: a role line shadowed by an earlier rule, the
role's own trust rule on `hostssl`, its own password rule above its trust rule, a shadowing rule that is not
`host all all`, and a file with no trailing newline. The count is deliberately not repeated here — `CASES`
and `AUDIT_CASES` in that file are the list.

It asserts twice over. Once against a reading of the file written independently of the code under test: the
first version of that tool asserted with a copy of `system.py`'s own regex, so every shape both missed
passed as correct — which is how a `hostssl` trust survived three rounds of it. And once against
**PostgreSQL itself**: it creates a throwaway cluster (`initdb` in a temp directory, its own port and
socket, TLS on like the supported host), points it at each fixture, and asks `pg_hba_file_rules` and a real
connection — which it skips, saying so, when those binaries are absent. It never touches the host's own
cluster.

It also runs **the plan's own verification step** against that cluster, over the states only a server knows
about: a rule it cannot parse (so it refused to load the file), a quoted `"all"`, roles named by pattern, a
blanket trust the rewriter left behind, a `hostnossl` rule for the role, and a properly narrowed file.

`verify_generated_shell.py` renders every generated script (both OpenUpgrade layouts, both interpreter
sources) and runs [ShellCheck](https://www.shellcheck.net) on it — install it with
`uv tool install shellcheck-py`, `pipx install shellcheck-py` or `apt install shellcheck`; it is a
development tool, never a dependency of the package. It is the static half and
`verify_migration_driver.py` the behavioural one: ShellCheck does *not* catch a failure masked by `;` in a
function whose last command succeeds, which is exactly the bug that verifier exists for.

`verify_workspace_versions.py` previews a plan, asks before applying (or not, with `--yes`), and removes
what it created. See
[`docs/workspace/layout.md`](docs/workspace/layout.md#re-verifying-every-version) for when to run it.

`verify_support_matrix.py` exits non-zero on drift and never edits the declared matrix: fixing drift means editing
`odoo_dwg/models.py` and `docs/reference/support-matrix.md` together. The editor check has its own procedure for
acting on what it reports: [`docs/workspace/editor.md`](docs/workspace/editor.md). There is no scheduled job running it — make it a
habit before touching the matrix, and every few months otherwise, since a bound drifts when *Odoo* changes,
not when this repository does.

## Commits

Conventional Commits, imperative mood, one logical change per commit. User-facing changes get a line under
`## [Unreleased]` in `CHANGELOG.md`.

## Security

See [SECURITY.md](SECURITY.md) — report vulnerabilities privately, never via public issues.
