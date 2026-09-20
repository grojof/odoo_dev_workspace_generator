# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Outbound firewall and mail capture** (change `add-egress-control`), both opt-in in `provision apply`, see
  [`docs/egress-control.md`](docs/egress-control.md).
  - **OpenSnitch 1.8.0** is installed from the upstream release, with SHA-512 pinned from the maintainer-signed
    list.
  - **Hardened configuration:** deny by default whether or not its window is open, `proc` process monitoring
    (`ebpf` lost long-running processes on WSL), rules applied to connections without a visible process
    (WSL's localhost relay, so the Mailpit UI opens from Windows), no connection flush on start, and fail
    closed.
  - **Baseline `00-odwg-*` rules** that come before any other rule:
    - localhost, DNS, NTP and the VS Code server;
    - **Odoo (`odoo-bin`) rejected everywhere but localhost** (and DNS on port 53, which every process may
      use);
    - GitHub, PyPI, `uv`, the Ubuntu archives and npm for the development tools.
  - **Mailpit 1.31.2** runs as a loopback-only service. Workspace and migration `odoo.conf` send mail to it.
  - **Redirect a database's mail to Mailpit** retargets a rehearsal copy's own mail servers and stops fetchmail,
    on Odoo 12–19.
  - **Every firewall decision reaches the system journal** (`journalctl -t opensnitch`), with or without its
    window.
  - **A `provision` submenu** turns each component off or on, persistently across restarts, or uninstalls it.
    For OpenSnitch it shows what `apt` will remove first and keeps your own rules.
  - `provision check` reports both and flags a softened firewall configuration.
  - `tools/verify_egress_pins.py` re-checks the pins, the signature and the signing key against upstream.

### Changed
- **The tests now guard the contract the tool is built on.** An audit of the suite itself mutated the source
  ~55 ways and found 37 mutations that no test noticed: the preview and the "Apply this plan now?" gate could
  both be deleted, `confirm_with_phrase` could accept anything, four of the five destructive phrase gates
  could be removed, `choose` could return the first option where it had returned "cancelled", and an
  unrecognised answer to a yes/no question could become a yes. Every one of those is now caught, along with
  the `pg_hba` probe's three unknown-state guards, the driver's `umask`/`set -euo pipefail`, the clone's
  staging path, the ready marker's write order, and `--lang`/`ODWG_LANG`/`--verbose`. One test asserted
  nothing at all unless a sentinel appeared in the output, and now fails if it does not.
- **The migration guide covers what the operator actually has to do**: the `pg_dump -Fc` to take (it was
  described but never shown), the **filestore** to copy alongside it (mentioned nowhere before — every
  `ir_attachment` in the migrated database would have pointed at a file that was never there), what to do
  when a step fails (read the named log; the cause is usually a custom module under
  `addons/odoo<major>/custom`), and what to do when it finishes: how to start Odoo on the migrated database
  and how to take it away.
- Both reader paths now point at their next station: `wsl-setup` and `provisioning` end on creating a first
  workspace, and `README.md` says what "provision is optional" means — you may prepare the host yourself,
  but a workspace needs PostgreSQL, the role and wkhtmltopdf either way.

- **`provision check` reads the loopback rules from PostgreSQL, not from `pg_hba.conf`** (change
  `read-pg-hba-from-the-server`). `pg_hba_file_rules` is the server's own parse: continued records folded,
  `include`/`include_dir` resolved and attributed to the file each rule came from, list fields split. Four
  audit rounds had found the same defect in four disguises — a blanket trust written `localhost`, indented,
  on an address that merely contains loopback, and finally on `hostssl`, which is the rule a loopback
  connection is matched against on a host with `ssl = on`. The address-by-address matching that kept missing
  them is gone.
- **`provision apply` verifies its own rewrite against the server** before connecting as the role: no rule
  may still trust every role — naming the file and line, which may be one the rewriter never saw — and the
  first rule PostgreSQL matches for the role must be the one the step added.
- `tools/verify_pg_hba_trust.py` asserts against a throwaway PostgreSQL cluster it creates and destroys,
  and against a reading of the file written independently of the code under test. It had been asserting with
  a copy of that code's own regex, which is why it passed a `hostssl` trust three rounds running.
- **A plan now reports one line per step** while it runs, keeping any warning a step printed, and printing the
  end of a failed step's output before it stops. `--verbose` (or `ODWG_VERBOSE=1`) streams every line as
  before.
- **Loopback `trust` is granted to the development role only.** A blanket trust let any local user connect as
  the `postgres` superuser. Re-run `provision apply` to narrow an existing host; other roles then need a
  password over loopback.
- **Root downloads go to `/var/cache/odoo_dwg`,** created fresh and root-only, instead of a predictable `/tmp`
  path another local user could own between the checksum and the install.
- **The firewall's DNS rule is limited to port 53.** It allowed the resolver's every port to every process,
  which on WSL is the Windows host.
- **Profiles are validated whenever they are loaded**, including when a workspace is managed. Versions must be
  exactly one of `12.0` … `19.0`; OCA repository names, `db_host`, ports and Python versions are checked too.
  **BREAKING** only for profiles that relied on looser values such as `"18"`.
- The unused `addon_prefix` profile field is gone. Old profiles that carry it still load, and it is ignored.
- `provision check` and the migration preflight **never ask for a password**. PostgreSQL's state and version
  come from `pg_lsclusters`; the development role is checked by logging in as it, or through `sudo -n`. When
  neither works, the role row says it could not be checked (WARN) instead of MISSING.
- **Refresh generated files** keeps a dated backup (`<file>.bak-<date>`), so a later refresh never overwrites
  an earlier one.
- The outbound firewall's development-infrastructure rule also allows the Ubuntu archive's country mirrors
  (`es.archive.ubuntu.com`, …).
- **The generated `odoo.conf` no longer sets `dev_mode = reload`.** It is inert until `watchdog` is
  installed, and from then on it re-executes Odoo on every file change, detaching the debugger that each
  launch configuration attaches. Generated configs now set `dev_mode = qweb,xml`; run **Refresh generated
  files** to update an existing workspace.
- The per-workspace README's layout tree lists `.vscode/`, `workspace.json` and `README.md`, which it
  generates but did not name.
- `tools/verify_generated_shell.py` runs ShellCheck over every generated script (it found two defects on its
  first run: dead variables in `setup_venv.sh`, and a failure path written as `a && b || c`).
- **The operator surface has a specification** (change `name-the-operator-surface`). The twelve capabilities
  all described what the tool does to the *host*: nothing described the CLI, the language, the menus, the
  file browser or the error handling, and "previewed and confirmed" was restated in six capabilities with no
  one place defining what a preview shows or what applying reports. Two capabilities now do —
  `command-plan` and `operator-interface` — and `openspec validate --specs` covers 14.
- **Each migration environment upgrades its own database.** Every environment used to share one database
  called `migration`, so a second driver could drop the first one's database between its steps and the first
  would then upgrade — and checkpoint — the second's data as its own. The name is derived from the chain
  (`migration_13_to_18`). An environment generated before this left a database called `migration` behind:
  **Clean a migration environment** now says so, and you can drop it once no environment still uses it.
- **Adding a version to a workspace says which ports move.** Ports are derived from a version's rank, so
  adding an older major renumbers every version above it — visible before only by reading the heredoc bodies
  in the preview, while a running instance kept a port its config no longer named.
- **Cleaning a migration environment names the staged modules it is about to delete**, before asking for the
  phrase. `rm -rf <root>` takes `addons/odoo<major>/custom`, which is where the operator's own migrated code
  lives, and the confirmation named only the directory.
- **The staging report says that each stage directory is a throwaway git repository**, which staging creates
  because `odoo-module-migrate` refuses to run outside one. An operator used to find a `.git` they had not
  made, holding their code.

### Fixed
- **`~/.psqlrc` could still change what five `psql` commands did.** An earlier round added `-X` to the
  probes it found; the version probe, the role-login probe, the role-existence probe, `psql_scalar` and the
  mail redirect did not have it. A test now asserts it for every `psql` the probes run.
- **A migration started before 0.2.0 refused to resume, and said to delete every checkpoint.** The driver
  binds a run to its source dump by a SHA it records beside the checkpoints; an environment generated before
  that has checkpoints and no recorded SHA, which read as *"came from another source dump — remove that whole
  directory to start over"*. It was not another dump, it was an unknown one, and the remedy threw away every
  completed step of a chain. The three states are now told apart, and the unknown one prints the command that
  adopts those checkpoints for the dump you have.
- **A venv built with an unsupported interpreter is now called out** when a workspace's files are refreshed.
  The interpreter on disk is what the regenerated files describe and rebuild, so an out-of-range one was
  quietly baked back in; the README says so too.
- **Refreshing a workspace warns about OCA repos that are in the profile but not on disk.** The profile is
  the documented way to add one, there is no menu action for it, and the refresh wrote the repo into every
  `addons_path` while cloning and linking nothing.
- **A profile the tool cannot use now says what to do about it.** Every action for that workspace goes
  through the same load, including the one that would repair it.
- **A file name in a staged module could write code into the generated
  `pre-migration.py`.** The scaffold put each finding's path into a `#` comment unescaped, and that path
  comes from the operator's copy of a client's module — a tree this tool did not write, where a file name
  may contain a newline. OpenUpgrade *executes* that file, while its own header says it does nothing. Paths
  are now written escaped, in the scaffold and in the staging report, and the report's fence is longer than
  any run of backticks in the tool log it quotes.
- **Migration checkpoints and logs were world-readable.** A checkpoint is a `pg_dump` of the restored copy
  of a customer's production database. The driver now runs under `umask 077` and both directories are
  `700` — it relied entirely on the home directory's mode before. An environment that already exists is
  narrowed the next time you generate over it, or the next time its regenerated driver runs; upgrading the
  tool alone changes nothing on disk, and files already inside those directories keep the mode they have.
- **A restored database could repaint the terminal.** Module names and authors are read from the database
  under migration and printed in the preflight table; only colour was ever stripped, so `\x1b[2J` or an OSC
  sequence reached the terminal and was counted in the column width. Table cells now carry colour and
  nothing else.
- **Scanning custom modules for breaking names took minutes and usually found nothing.** Each module's
  source was scanned once per analysis record — 75,000 of them in one step — and the step's records were
  re-read once per module. The names are looked up now instead of searched for one by one: the same 75,000
  records over the same source went from **571 s to 0.7 s**, with identical output on 600 randomised
  differential trials.
- **`~/.psqlrc` could change what the generated driver did**, invisibly: one `psql` in its host preflight
  ran without `-X`, unlike every other in the project.
- **An unreadable directory ended the whole flow** instead of the file browser saying so and stepping back
  out, and a profile too deeply nested for `json` to parse was reported without naming the profile.
- **`apriori.py` could abort a preflight run**: a non-UTF-8 byte or a key `ast` cannot evaluate raised
  instead of degrading to "renames unknown", in the Python reader and in the driver's rendered one.
- **A `trust` for every role on one database was invisible to `provision`** (change
  `agree-on-what-a-trust-rule-covers`). The classification asked for the rule's *database* field to be `all`
  as well as its role field, so `host mydb all 127.0.0.1/32 trust` passed the check, survived apply and was
  accepted by the verification step. Against a real server that rule lets any local user connect to `mydb`
  as `postgres` — superuser, `pg_execute_server_program` included. A blanket trust is now any TCP `trust`
  rule whose **role field** is the keyword `all`, on any database.
- **A quote anywhere on a rule's line excused it.** The exception exists because `"all"` is a role *named*
  `all`, which PostgreSQL does not match a connection against — but it was implemented as any double quote
  on the line, and the server accepts `host all all "127.0.0.1/32" trust` like any other blanket trust. Only
  the role's own field is read now.
- **`provision apply` could fail on a host it could never finish provisioning.** The rewriter decided
  whether the role's line was *reached* by matching one line shape (`host all all`), while the check and the
  verification step stop at the first rule matching the connection, whatever its shape. With
  `host mydb all 127.0.0.1/32 md5` — or the role's own `scram-sha-256` rule — above its trust line, the
  rewriter reported success having inserted nothing and the verification step then failed; re-running gave
  the same two answers. All three now read the same fields, and `tools/verify_pg_hba_trust.py` runs the real
  rewriter and the real verification SQL over both cases against a throwaway PostgreSQL.
- **"Stage custom modules" was unusable on a host with `commit.gpgsign = true`.** The throwaway commit the
  staging step makes inherited the operator's git config, and git exits 128 when it cannot sign as the
  identity the step interpolates — after the module had already been copied, so the next attempt demanded
  the `RESTAGE` phrase to reach the same failure. That commit is now independent of the global config
  (`--no-gpg-sign`, `--no-verify`, no hooks path), as its `-c user.name`/`-c user.email` already intended.
- **A workspace generation interrupted before its profile was written was a dead end**: create refused the
  directory ("already exists"), manage refused to load it ("no workspace.json"), and the name was taken
  until the operator deleted the tree by hand. `workspace.json` is written first now, so **Manage → Refresh
  generated files** completes an interrupted tree.
- **A file's mode could be left unset and never repaired.** Writing a file and setting its mode were two
  steps, so an interruption between them left a script that was not executable — and a refresh, which
  compares content only, then reported the workspace up to date. They are one step now.
- **A migration environment's generated files were overwritten with no backup**, while the workspace surface
  promises one in writing. A step's `odoo.conf` that would change is kept as `<file>.bak-<date>` first.
- The migration flow shows the interpreter **a step's venv was really built with** when it differs from the
  one about to be planned, so a pin that was never persisted is visible before the preview rather than
  silently rebuilt away.

- **A newly generated workspace dead-ended at F5.** Its README never said to create a database, so the
  debugger's default (the workspace name) hit `database "<name>" does not exist`. The README now opens with
  the `createdb` to run, the URL to open, Odoo's own database manager and its `admin_passwd`, where mail
  goes (Mailpit on `:8025`), and the fact that `setup_venv.sh` *re*builds venvs the generation already made.
- **The one `createdb` in the docs could not work on a host this tool provisions.** The development role is
  trusted over loopback TCP, not over the Unix socket, so a bare `createdb` fails with `role "<you>" does
  not exist`. Every `createdb`/`dropdb` shown — in the docs and in the tool's own message — now carries
  `-h 127.0.0.1 -U odoo`.
- **A contributor could not run the first command in CONTRIBUTING.md.** There was no development-environment
  section, and the `openspec` CLI (a Node package) was named nowhere in the repository. Both are there now,
  along with what an OpenSpec change is made of, for a human rather than an agent.

- **A host whose `pg_hba.conf` already trusted the development role on `hostssl` could not be provisioned
  at all.** The rewriter counted any `host…` type as the role's trust line and so inserted nothing, while
  the check and the verification had been tightened to plain `host` — the step then failed on a rule it had
  never added, and re-running did the same. All three agree now.
- **The patched wkhtmltopdf's install reported success without being the binary on `PATH`.** It is read
  back after installing, and the step fails naming what it found, since an unpatched distribution build
  earlier on `PATH` is exactly the state the step exists to fix.
- **A service that started and died left the run saying "Provisioning applied".** `systemctl restart`
  returns as soon as a `Type=simple` unit is forked, and OpenSnitch's unit is one. The firewall and the mail
  capture now have their state read back and reported once the plan has run.
- **The generated `setup_venv.sh` could leave a half-built venv wearing its ready marker.** Neither
  `uv venv --seed` nor `python3 -m venv` removes the marker, so a run that died during `pip install` left
  every later flow skipping that venv. The script clears the marker first and writes it last, as the plan
  already did.
- `provision check` reads the rules on a PostgreSQL older than 15 too, where `file_name` does not exist —
  the apply side already branched for it, the check side did not.
- Every `psql` the plan runs carries `-X` (four did not), pathname expansion is off while the verification
  walks its findings, and the step's own name no longer promises more than it reads: the view is the file as
  the server parses it now, and the connection check is what proves the loaded rules.

- **A `pg_hba.conf` PostgreSQL refuses to load made `provision apply` report success on a host it had not
  changed.** `pg_ctl reload` returns 0 whether or not the file parsed, so with one malformed rule anywhere
  the server keeps its previous rules while the file on disk reads as narrowed — and the verification step,
  which reads the file, agreed. The connection check then passed *through the blanket trust that was still
  live*. Reproduced against a real server: `postgres` still connected over TCP with no password while all
  four steps reported OK. The verification now refuses any file the server reports a parse error for, naming
  the line.
- **A rule for roles named by pattern (`/…`) or group (`+…`) was invisible.** It reaches every member
  without spelling `all`, so a `trust` written that way was neither narrowed nor reported. Neither the check
  nor apply can tell whether such a rule covers every role, so both now say so instead of passing.
- **A role literally named `"all"` could block apply forever.** The check knew `"all"` is not the keyword;
  the verification step did not, so it failed on a rule nothing could ever narrow, on a host that was in
  fact correct. Both sides read the rule's own line now, and the check handles more than one such rule.
- **A `hostnossl` trust rule for the development role counted as "reached".** With `ssl = on` — the
  supported host's default — that rule is never consulted, so the check reported a narrowed host where the
  role could not connect at all. Only a plain `host` rule counts as reached; every type still shadows.
- The plan's `psql` calls run with `-X`, so the `postgres` user's `~/.psqlrc` cannot end up inside a parsed
  answer, and the verification survives a server older than PostgreSQL 15, where `file_name` does not exist.

- **A blanket `trust` written on any connection type but `host`/`hostnossl` was invisible to the
  narrowing** — and `hostssl` is not a corner case: Ubuntu 24.04 ships `ssl = on` and clients prefer TLS, so
  a `hostssl all all 127.0.0.1/32 trust` is the rule a loopback connection is actually matched against. It
  survived, the role's line was inserted *below* it, the closing connection check passed because of it, and
  `provision check` reported `trust for odoo only` while any local user could still connect as `postgres`.
  All five `host*` types are covered now, by a prefix that cannot miss a sixth.
- **A `pg_hba.conf` with no final newline had its last record fused with the inserted rule**, which
  PostgreSQL cannot parse. The append starts on a line of its own.
- **A file whose rules cannot be read one line at a time is refused, not rewritten**: a record continued
  with a trailing backslash, or rules pulled in with `include`/`include_if_exists`/`include_dir`. Narrowing
  what such a file shows while leaving the rest would report a success that did not happen.
- The role's line goes before the **first `host` rule of any kind**. Preferring a rule for every role could
  only push it later — behind a group-role rule, for instance, which would shadow it.

- **A blanket `trust` whose address merely *contained* loopback survived the narrowing** — `all` (what the
  official `postgres` image writes for `POSTGRES_HOST_AUTH_METHOD=trust`), `0.0.0.0/0`, `127.0.0.0/8` — and
  the check then reported `trust for odoo only`, with the network reachable in the `0.0.0.0/0` case. The
  rule is now recognised by its **method**, not by a list of addresses, which is what enumerating spellings
  kept getting wrong.
- **A role trust line that was present but shadowed counted as narrowed.** `pg_hba` is first-match-wins, so
  a line below a rule for every role is never read. Both the check and the step now ask whether the line is
  *reached*, and apply inserts one that is.
- **`pg_hba.conf` files that pull in rules through `include`, `include_if_exists` or `include_dir`** were
  read as if those rules did not exist. The check reads them like any other rule now, because PostgreSQL
  resolves the include; the text rewriter refuses such a file, naming what it cannot see, rather than
  narrowing the part of it that it can.
- **The migration preflight blamed the modules when the environment had never been generated.** With no
  clones on disk nothing resolves, so every installed module was reported missing and Odoo's own — `base`
  among them — as "dropped by Odoo". Both the interactive check and the driver's own coverage now say the
  step's sources are not on disk and classify nothing.
- **A migration step ran even when its OpenUpgrade code was not on disk.** Odoo says nothing when
  `--upgrade-path` names a directory that is not there — it finds no scripts — so a chain whose checkout was
  interrupted or partially deleted migrated nothing and still reported `[done] migration complete`, with a
  checkpoint per step. Each step now checks its own code first and aborts naming the missing directory.
- **A failing migration step died without a word.** It relied on `set -e`, while the reason sat in
  `logs/<version>.log`. It now aborts naming the step and that file.
- **A blanket loopback `trust` survived the narrowing when written indented, as `hostnossl`, or in the
  `address netmask` form** — and, as before, the check then reported `trust for odoo only`. The connection
  check added earlier cannot catch this one, because a surviving blanket trust is exactly what lets the role
  in. All three shapes are recognised now, by the rewriter and the check alike, and the role's own line is
  inserted before any rule that would match the same connection first.
- **Adding a version whose venv build failed reported success on the retry.** The second attempt saw the
  venv directory and skipped the build, so the workspace listed a version whose venv had no Odoo
  dependencies. Workspace venvs now carry the same ready marker migration venvs have had: written last, so
  it can only mean every install finished.
- The `pg_hba` connection check retries the connection it is actually proving, and its failure names both
  causes: PostgreSQL not running, or a rule above the ones it just added matching first.
- **`provision apply` reported "Host already provisioned — nothing to do" on a host with PostgreSQL stopped
  and no development role.** A probe that could not answer (a stopped server hides both the role and
  `pg_hba.conf`) was read as "nothing to do" instead of "do the work". Unknown now means act, and every step
  planned is idempotent.
- **A blanket loopback `trust` written as `localhost`, `samehost` or `samenet` survived the narrowing** and
  `provision check` then reported `trust for odoo only` — while any local user could still connect as
  `postgres`. Every spelling is recognised now, by the rewriter and by the check alike, and the step ends by
  connecting as the role: a line that is present but shadowed by an earlier rule fails the step instead of
  passing it. `tools/verify_pg_hba_trust.py` runs the rewriter over every shape of that file below.
- **Installing Odoo 12's requirements could report `[OK]` having installed only the `python-ldap`
  substitute.** The step is a `grep | pip` pipeline and plans run without `pipefail`, so `pip`'s status hid
  `grep`'s. The step sets `pipefail` now, as the generated `setup_venv.sh` always did.
- **A checkpoint that could not be written was reported as written.** `pg_dump`'s failure did not stop the
  driver — it printed `[checkpoint] <step>`, ran the rest of the chain and exited 0, leaving no recovery
  point at all. The run now aborts with a `[fail]` line naming the step, and removes the half-written file.
  `tools/verify_migration_driver.py` executes the generated driver against stub binaries so this class of
  bug cannot pass a text-only assertion again.
- **A plan step could swallow the operator's keystrokes.** Steps inherited the terminal's stdin, so an
  unexpected prompt (debconf, a credential helper) waited invisibly — its output is captured unless
  `--verbose` is on — and consumed the answer meant for the next question. Steps now run with stdin closed,
  and every `apt-get install`/`purge` runs with `DEBIAN_FRONTEND=noninteractive` so there is no dialog to
  begin with.
- **`provision apply` never narrowed `pg_hba.conf` on a host it had already provisioned** — exactly the
  hosts an earlier version left trusting every role over loopback. The narrowing is now planned whenever the
  rules are not in the wanted shape, `provision check` reports that shape, and the step fails loudly instead
  of silently doing nothing when the file has no rule to anchor to.
- **The firewall's Odoo rejection sorted after two allow rules.** Rules are evaluated in file-name order and
  the first match wins, so an allow (the VS Code server's) could have matched an `odoo-bin` process first.
  The rejection is now `00-odwg-003`, ahead of every allow rule that could match a user process — only the
  loopback, DNS and `systemd-timesyncd` rules precede it.
- A migration environment's database fields (`working_db`, `db_user`, `db_host`, `db_port`) are validated
  like a workspace profile's, since a hand-edited environment reaches the generated driver.
- A profile naming one of the class-level defaults (`base_dir`, `port_step`, …) raised a `TypeError` instead
  of being ignored like any other unknown key.
- An OCA link whose path already held a real directory got the symlink nested inside it; the step now
  replaces the link or fails.
- A `psql` failure inside the driver's database preflight aborted without saying which check failed.
- **Shell injection through versions and profiles.** A migration source or target such as `13.0$(…)`, or a
  version, name, `db_host` or OCA repository in a `workspace.json`, passed validation and reached generated
  scripts (`run_migration.sh`, `setup_venv.sh`, `run-odoo*.sh`) or `odoo.conf`. All of them are now validated.
  Generated scripts quote every path with `shlex.quote`.
- **The migration driver did not resume from the last good step.** It skipped completed steps, but re-ran a
  failed one on the half-migrated working database. It now restores the newest checkpoint first. It also
  binds the run to its source dump by SHA-256, and refuses a different dump instead of ignoring it.
- **Coverage for the ≤ 13 steps looked in the wrong places**, in the preflight and in the driver. That made
  every core module look "dropped by Odoo", and renames were read from the ≥ 14 location. Both now read the
  fork's own `addons`, `odoo/addons` and `openupgrade_records/lib/apriori.py`.
- **Pinning another Python for an already-built migration step had no effect.** The venv was kept because of
  its ready marker. It is now rebuilt when its `pyvenv.cfg` names another interpreter.
- **Add a version** added the version to the loaded profile even when its plan was declined or failed.
- **Invalid input crashed the CLI with a traceback:** a version like `3.x`, a malformed `workspace.json`, or a
  port given as text. It is now reported, and the CLI returns to the menu.
- **An interrupted OpenSnitch install could leave `/usr/sbin/policy-rc.d` behind,** which stopped every
  service from starting after later `apt` installs. It is removed on any exit, and a leftover of the tool's
  own is recognised.
- **The migration driver's coverage check never blocked.** Its helper reads a heredoc as its program, so the
  piped module list arrived empty and every module passed. A chain could start with custom modules missing.
  The list now travels in the environment, and an empty list is a failure.
- **Checkpoints from an earlier attempt were trusted.** A fresh run kept step dumps belonging to another dump
  and skipped those steps, reporting a migration "complete" that never ran. A fresh run now owns the
  checkpoint directory, a resume drops everything after the first gap, and checkpoints are written through a
  temp file so an interrupted dump is never mistaken for a finished one.
- **The role was reported MISSING when PostgreSQL was not running,** although it had not been checked.
- **`psql` could prompt** during the migration preflight; it now fails instead.
- **A `workspace.json` that is not a JSON object** raised a traceback.
- **The database named in the preflight, and staged module names, were not validated.**
- **An unparseable database version ended the whole preflight** instead of reporting one row.
- **`Add a version` wrote the profile before building the venv,** so a failed build left the version listed.
- **The interpreter prompt offered "keep the host python3"** on a host without one, which then cancelled.
- **Only the OpenSnitch daemon's version was checked,** so a missing UI package was never installed.
- **Smaller fixes:**
  - the OpenSnitch configuration is written atomically;
  - a missing `apriori.py` is no longer cached for the whole session;
  - `provision apply` says when no verified wkhtmltopdf is pinned for the host;
  - staging no longer hides `git` failures;
  - the Python 3.10 gevent repair matches any 3.10 patch level.
- **The rtlcss option (right-to-left languages) installed 455 packages.** `apt` added every recommended package, a GUI terminal among
  them. It now installs `nodejs` and `npm` without recommends, and the prompt says what the step is for:
  only right-to-left languages (Arabic, Hebrew, Persian…).

## [0.1.0] - 2026-09-19

First release.

### Added
- **Manage → Refresh generated files** (change `refresh-generated-files`) brings an existing workspace's
  generated files up to date with the tool.
  - It writes only the files whose content changed, and keeps each previous version as `<file>.bak`.
  - It reads each venv's interpreter from its `pyvenv.cfg`.
  - It never touches addons, venvs, clones or databases.
- The Spanish UI is complete, and a test now fails if an operator-facing string has no Spanish entry.
- **Debug configurations for the shell, module upgrades and tests** (change `add-odoo-shell-launch`). Each
  version's `launch.json` now has four debugpy configurations:
  - the server;
  - `odoo-bin shell` with `env` bound to a database;
  - the server upgrading modules on start (`-u`);
  - one module's tests (`--test-enable --test-tags /<module> --stop-after-init`).

  VS Code asks for the database and modules when a configuration starts. The generated README lists them, and
  `tools/verify_workspace_versions.py` now runs them from the generated file on every version.
- **Official Odoo extension support** (change `use-official-odoo-language-server`). Generated workspaces carry
  an `odools.toml` for the official language server (OdooLS): one profile per Odoo version ≥ 14 (OdooLS
  refuses older ones), using only the four documented minimal keys — `name`, `odoo_path`, `addons_paths`,
  `python_path` — as absolute paths, so the file stays valid across releases of a strict schema. Pick the
  profile from the status bar. New `tools/verify_odools_config.py` checks the emitted keys against the latest
  stable release's published schema, lists keys not yet emitted, and prints the release notes since the
  release last reviewed; [`docs/editor-integration.md`](docs/editor-integration.md) documents the update
  procedure.
- **Support matrix** (change `add-support-matrix`): one authoritative, evidence-tiered declaration of what
  the tool supports — host releases, the tool's own Python floor, and per-Odoo-version Python range,
  recommended interpreter and PostgreSQL floor — in `models.py` (`ODOO_SUPPORT`/`SUPPORTED_HOSTS`), which
  `provision check`, workspace generation and migration all read instead of restating. Each bound carries
  its evidence tier (`official` / `derived` / `untested`) and source, so output never presents a derived
  bound as an Odoo requirement. New `docs/support-matrix.md` cites every fact verbatim and records the
  retrieval procedure; new `tools/verify_support_matrix.py` (stdlib-only, outside the package and the test
  suite) re-derives every bound from its official source and exits non-zero on drift.
- **Per-version Python maxima**, which the tool did not model before, derived from the newest interpreter
  bucket each Odoo branch declares in its own `requirements.txt` and the distribution its comment names
  (Jammy/Noble/Trixie/Resolute) — a derivation that reproduces Odoo 19's declared `MAX_PY_VERSION = (3, 14)`
  exactly. Odoo 12/13 declare no ceiling and are marked `untested` rather than assumed.
- **Interpreter selection when building environments.** Workspace generation builds each venv with the host
  `python3` while it is inside that version's range, and otherwise reports the range, the detected version
  and the crossed bound's tier and offers a matching `uv`-provisioned interpreter (`uv venv --seed`, so the
  venv still has `pip`). Migration environments take each step's interpreter from the matrix recommendation
  and let the operator **pin any step** to a specific Python — the way to rehearse on a client's own
  interpreter — with the step's requirements repair following the interpreter actually in use. Every step
  can be pinned, 13 included, since no step runs in a container any more.
- `provision check` now reports the host release against the supported list, the installed PostgreSQL server
  version against the floor of the versions in play, the host `python3`, and which interpreters `uv` can
  provide.

- **`tools/verify_workspace_versions.py`**: builds a throwaway workspace with every supported Odoo version
  through the tool's own plan, installs `base` and serves `/web/login` on each, then removes what it created.
  It is the documented procedure for re-checking that every version still builds and starts
  ([`docs/workspace-layout.md`](docs/workspace-layout.md#re-verifying-every-version)).
- **The generated README states what each venv installs**: its Python (host or `uv`), its setuptools rule
  and any requirement replaced, with the reason, so anyone reading the workspace, human or assistant, knows
  exactly what runs. `docs/workspace-layout.md` carries the same table for every version, as last verified.

### Changed
- Workspaces recommend the **official** `Odoo.odoo` extension instead of the third-party
  `trinhanhngoc.vscode-odoo`, and set `python.languageServer` to `None` so Pylance does not analyse Python
  alongside OdooLS. No `jsconfig.json` is generated: OdooLS 1.5 resolves JavaScript and OWL itself.
- **BREAKING — Docker is no longer used or required** (change `drop-docker-run-13-natively`). The Odoo 13
  step, the only step that ever ran in a container, now runs natively in a `uv` virtualenv on Python 3.8
  like every other step. `provision check` drops the Docker rows, `provision apply` drops the Docker Engine
  install and the `odoo:13.0`/`odoo:12.0` image pulls, and the migration preflight and driver stop requiring
  a daemon. A host that installed Docker for earlier versions can keep or remove it freely.

- **BREAKING — Ubuntu 24.04 is the only supported host**, narrowed from the whole Debian/Ubuntu apt family
  (changes `add-support-matrix`, then `lighten-scope`). `provision check` reports any other host as
  unsupported (it still completes and still changes nothing) and `provision apply` refuses before assembling a
  single command. Debian and Ubuntu 22.04 had been declared but never run on a real host, so the claim was
  dropped rather than left implied.
- **BREAKING — the tool needs Python 3.12** (24.04's system Python; `requires-python = ">=3.12"`), up from
  3.10, which existed only to honour 22.04.
- **Workspace clones are shallow** (`--depth 1`, Odoo and OCA alike), with no option to configure. A full
  single-branch Odoo clone measured 4.2–5.7 GB, almost all history; a shallow one is about 1 GB. Existing clones
  are left untouched, **Refresh shared repos** keeps working, and `git fetch --unshallow` restores history for
  whoever needs `log`/`blame`.
- **Workspaces connect as the shared `odoo` role by default** (change `default-shared-db-role`), the role
  `provision apply` creates by default and migration environments use. `db_user` used to default to the
  workspace name, a role nobody had created, so a freshly provisioned host could not serve a new workspace.
  Existing workspaces keep their role (it is recorded in `workspace.json`); a profile can still set
  `db_user`. Odoo's database selector now lists every development database on the host.

### Fixed
- **Add a version** rewrote every generated file without the interpreters, so `setup_venv.sh` and the README
  of a workspace with a `uv` venv claimed the host `python3`. It also overwrote hand edits. It now keeps each
  venv's interpreter and backs up what it changes.
- Generated files carried an extra blank line at the end. They now hold exactly the rendered content.
- **PostgreSQL role names are validated.** The role typed into `provision apply` was interpolated unquoted
  into SQL run as `postgres`, and a profile's `db_user` was written through a shell heredoc; both now must
  be a plain PostgreSQL identifier (`^[a-z_][a-z0-9_]{0,62}$`) and are rejected before any plan is built.
- **Workspace venvs for Odoo ≤ 16 failed to start, and Odoo ≤ 13 venvs failed to build** (change
  `fix-workspace-venvs`). The venv step installed the latest setuptools: on Python 3.12 that is 81+, which
  no longer ships the `pkg_resources` Odoo ≤ 16 imports at startup (`ModuleNotFoundError` on F5 in an Odoo 15
  workspace), and for Odoo ≤ 13 `vatnumber==1.2` cannot build with setuptools ≥ 58 (`use_2to3 is invalid`).
  Workspace venvs now install `setuptools<58` (≤ 13), `setuptools<81` (14–16) or an unpinned one (≥ 17), in the
  plan and in `setup_venv.sh` alike. The migration already pinned it and is unchanged. Odoo 12/13 workspaces
  also defaulted to the host's Python 3.12 — their maximum is unstated, and an unstated maximum bounded
  nothing — where their pinned `gevent` does not build; they now default to the recommended `uv` 3.8, and
  the prompt says the host is unproven rather than out of range. And Odoo 12 venvs install `python-ldap==3.1.0`
  in place of the deprecated `pyldap==2.4.28`, which does not build on `uv`'s Python 3.8.
- **Generated files can no longer break out of their heredoc.** Every file is written with a quoted
  heredoc whose delimiter was a fixed `EOF`, so a profile value carrying a newline and a line `EOF` (a
  hand-edited `db_host`, `addon_prefix` or OCA repo name) ended the heredoc early and ran the rest as shell
  commands — reproduced before the fix. The delimiter is now chosen so that no content line equals it.
- **The containerised Odoo 13 step silently under-migrated.** The `odoo:13.0` image sets
  `addons_path = /mnt/extra-addons`, so the mounted OpenUpgrade fork's `odoo-bin` loaded the *image's*
  add-ons; in the ≤ 13 layout every migration script lives inside its add-on, so only core scripts ran and
  the step still reported success. Measured against the same database: the container left
  `iap_account.company_id` untouched and the orphan column survived to Odoo 19, where the model declares
  `company_ids`; with IAP accounts present, the post-migration that moves the data would never run. The
  native step names the fork's `addons` directory explicitly and applies those scripts. Verified on WSL:
  a full 12 → 19 chain now ends with `openupgrade_legacy_13_0_company_id` and the `company_ids` relation,
  and no orphan column.
- The Odoo 13 requirements need `setuptools<58` as a **build** constraint (`vatnumber==1.2` still calls
  `use_2to3`). Build constraints are generated per version as `requirements/constraints-<ver>.txt` and
  applied with `uv pip install --build-constraints`, separate from the existing requirement overrides.
- **A real 12 → 19 migration could not run at all** (change `fix-preflight-coverage-classification`), which
  the first end-to-end run against an Odoo 12 database built from Odoo's own demo data exposed:
  - The per-step addons coverage check treated every installed module as the operator's code, so core
    modules Odoo renamed (`web_editor` → `html_editor`), merged (`web_kanban_gauge` → `web`) or deleted
    (`web_settings_dashboard`, `web_diagram`) each aborted the driver with "place it in
    `addons/odoo<major>/custom`". They are `auto_install` dependencies of `base`, so every Odoo 12 database
    hit it. Coverage now resolves the renames and merges OpenUpgrade declares in its own `apriori.py`, and
    classifies what is left by author: Odoo's own dropped code warns, anyone else's blocks. The driver
    refuses only on the blocking class.
  - Steps running Odoo ≤ 16 died at import with `ModuleNotFoundError: No module named 'pkg_resources'`.
    Nothing declares `setuptools`, so it arrived transitively and its version followed the step's
    interpreter — the 3.8 steps resolved 75.x and worked, the 3.10 steps resolved 84.x and failed.
    Those venvs now pin `setuptools<81`.
  - Accepted on WSL Ubuntu 24.04: 12 → 19 completed with eight checkpoints and the database at
    `base 19.0.1.3`, data intact, `html_editor` installed and the dropped modules gone.
- Odoo 19's PostgreSQL floor was carried as 12; it is 13 ("Changed in version 19: Minimum requirement
  updated from PostgreSQL 12 to PostgreSQL 13").
- The Odoo 15/16 Python floor (3.7) was an uncited assumption and is now anchored to both the documentation
  and `setup.py`. Odoo 14's documentation/`setup.py` divergence (3.7 vs `>=3.6`) is recorded rather than
  silently resolved.
- All nine capability specs carried the placeholder `## Purpose` that `openspec archive` writes, which
  `openspec validate --specs` warned about on every run; each now states what its capability is for.
- F0 foundation: package skeleton `odoo_dwg/` (i18n, ui, prompts, system, models, cli, workflow stubs),
  root entry point, interactive menu and argparse CLI (`workspace`/`provision`/`migrate`).
- English-canonical UI with an optional Spanish catalog (`ODWG_LANG=en|es`).
- Domain model: `WorkspaceConfig`/`InstanceConfig`, official Python-floor facts, deterministic per-version
  ports, JSON round-trip.
- Project conventions: `CLAUDE.md`, OpenSpec initialized (`openspec/`, `.claude/`), `docs/roadmap.md`,
  robust `README.md`, `pyproject.toml` (ruff + pytest, zero runtime dependencies).
- Unit tests for `models` and `i18n`.
- **F1 workspace section**: JSON-profile-driven generation of a per-client workspace — shared repo cache
  (`git clone --branch <ver> --single-branch`), per-version `odoo.conf`, per-instance venv, `addons-custom`/
  per-version `addons-oca` symlinks, VSCode files, `scripts/`, and a robust per-workspace README. Pure
  `templates.py` + `planners.py` (`plan_repo_cache`/`plan_workspace_tree`/`plan_build_venv`/
  `plan_generate_workspace`/`plan_refresh_repos`); create-only vs manage-only flows in `workflows/workspace.py`
  over plan → preview → apply. Example profile in `examples/`. Docs: `docs/workspace-layout.md`,
  `docs/configuration-reference.md`.
- **F2 provision section**: host-agnostic (Debian/Ubuntu apt) system provisioning. `provision check` renders a
  read-only host-readiness table; `provision apply` (root-gated, previewed, idempotent) installs the Odoo
  build dependencies, PostgreSQL + a dev role (with loopback trust for development), the checksum-verified
  patched wkhtmltopdf (0.12.6 for Odoo ≥ 15), and optional Node + rtlcss. New `provisioning.py` (facts + pure
  `provision_rows`), provision planners in `planners.py`, host probes in `system.py`, wired in
  `workflows/provision.py`. Docs: `docs/provisioning.md`. Validated end-to-end on WSL Ubuntu 24.04.
- **F3 migration mode**: generates an OpenUpgrade migration environment for a source → target chain
  (sequential, no skips). Data-backed interpreter strategy (measured on WSL): `uv` native interpreters for
  Odoo ≥ 14 (14/15→3.8, 16/17→3.10, 18/19→3.12) and a Docker fallback (`odoo:13.0`/`odoo:12.0`) for the
  Python-3.6/3.5 steps. `MigrationEnv` + `migration_chain`/`migration_interpreter` in `models.py`; migration
  planners (`plan_migration_clones`/`plan_migration_venvs`/`plan_migration_configs`/`plan_generate_migration`)
  and templates (per-step `odoo.conf`, checkpointing `run_migration.sh`, Docker recipe); wired in
  `workflows/migration.py`. Docs: `docs/migration.md`.

- Migration menu: **Clean a migration environment** — removes a `<src>-to-<tgt>` environment directory
  (venvs, configs, checkpoints, logs, requirements, driver) over plan → preview → apply with an
  exact-phrase confirmation (`DELETE`); optionally also the shared `.repos` clone cache (opt-in, it
  serves every environment). The PostgreSQL migration database is deliberately untouched.

- **Migration preflight & Docker readiness** (change `add-migration-preflight`): `provision check` now
  reports `uv` and Docker (binary / daemon / OpenUpgrade fallback images as distinct signals) and
  `provision apply` gains opt-in plans for Docker Engine (`docker.io`) and `docker pull odoo:13.0`/`12.0`.
  New migration-menu **Preflight check** (chain-scoped host checks — Docker rows only when the chain has a
  12/13 step —, PostgreSQL/role, dump integrity via `pg_restore --list`, and against a named database:
  actual source version from `ir_module_module`, installed modules, per-step addons coverage naming the
  exact directory to fill, and a per-custom-module adaptation warning). The generate flow shows the host
  preflight first (MISSING requires explicit confirmation) and `run_migration.sh` embeds the same checks:
  host before restore, database right after the initial restore and before step 1, aborting non-zero with
  the failed check named. Migration environments now define `addons/odoo<major>/{custom,oca}` per version,
  threaded into each step's `addons_path` ahead of OpenUpgrade and core.

- **Custom-module staging** (change `add-custom-module-staging`): migration menu action **Stage custom
  modules** — per chain step it copies the previous stage's code into `addons/odoo<major>/custom` and runs
  OCA `odoo-module-migrator` for exactly that bump (tool installed into a shared uv venv via a previewed
  plan; the operator's source is never modified), cross-references the staged code against the step's
  OpenUpgrade `upgrade_analysis.txt` files (removed core fields/models → candidate findings with
  file:line; generic names excluded), writes inert `pre-migration.py` scaffolds (never overwriting —
  `pre-migration.generated.py` beside existing files), and produces `staging/report-<module>.md` with the
  tool log verbatim. Staging is a prepared starting point; developer review completes the migration.

- New `docs/wsl-setup.md`: a step-by-step guide to set up an Ubuntu 24.04 host on WSL 2 for the tool
  (install, user creation, systemd check, optional custom instance name, cloning into the Linux file
  system, `provision` check/apply, optional `uv`/Docker and editor setup). Anchored to Microsoft Learn;
  linked from the README. The tool still never creates a host — the environment stays the user's.

- Docs refreshed to the eunomai living-docs v2 standard with the **CLI-tool profile**: new
  `docs/commands.md` (full command/menu/phrase reference), README reshaped as a product map (Mermaid
  plan→preview→apply flowchart, real invocations, surface-organized index), new `SECURITY.md` (private
  reporting via GitHub Security Advisories) and `CONTRIBUTING.md`; `docs-check` green.
- Migration step configs now put the OpenUpgrade checkout **root** on `addons_path` (previously the
  `openupgrade_scripts` module directory itself), so `openupgrade_framework` resolves as the official
  OpenUpgrade run instructions require.
- Migration environment generation failed at the first requirements-overrides write
  (`cat > .../requirements/overrides-<ver>.txt`: "No such file or directory"): the `mkdir -p` for
  `requirements/` ran only in the configs planner, *after* the venvs planner that writes the overrides.
  `plan_migration_venvs` now creates the directory itself before its first write (found running a real
  12 → 18 generation on WSL).
- Migration venvs are now created with `uv venv --no-project`: without it, uv discovers any
  `pyproject.toml` at the caller's working directory (e.g. this repo's own, `requires-python >=3.10`)
  and emits a spurious incompatibility warning when building the 3.8 venvs for Odoo 14/15.
- The migration `requirements/overrides-<ver>.txt` was written but never applied; the requirements
  install now passes it via `uv pip install --overrides`. Its content is no longer a placeholder:
  for the Python-3.10 steps (Odoo 16/17, whose branches pin `gevent==21.8.0` — no cp310 wheel and an
  sdist that no longer compiles under modern Cython) it lifts to the branches' own 3.11 pins,
  `gevent==22.10.2` + `greenlet==2.0.2`. Validated with a real install on WSL.
- Interrupted venv builds now resume correctly: each finished venv is stamped with a `.odwg-ready`
  marker and the venvs planner skips on the marker (not the venv directory), rebuilding half-built
  venvs with `uv venv --clear` instead of silently skipping them.

[Unreleased]: https://github.com/grojof/odoo_dev_workspace_generator/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/grojof/odoo_dev_workspace_generator/releases/tag/v0.1.0
