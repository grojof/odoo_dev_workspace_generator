# Design

## Context

- The first client intake was done with ad-hoc scripts. Its six traps are listed in the proposal, and each
  one below is answered by a decision.
- The source version is built today by `plan_seed_environment`: official Odoo at the branch head, a venv,
  and an empty `custom`/`oca` layout.
- `open_for_testing.sh` covers the chain's steps only.
- Findings go to the ledger through `findings.add_findings`.
- Neutralisation and its guard exist; the guarded start reuses them.

## Goals / Non-Goals

**Goals:**
- Every classification is pure and unit-tested on invented fixtures.
- What only a real tool can prove (`pg_restore`, PostgreSQL grants, git history with merges) is proved by
  `tools/verify_intake.py` against throwaway instances.
- The source instance is the client's: its core at its commit, its add-ons in its order, started guarded.

**Non-Goals:**
- Outbound inventory as findings, availability across all OCA repositories, and the custom-code network
  scan. These belong to the follow-up change.
- Writing client-facing text automatically. Findings are recorded in English with `audience`. The
  operator writes the client text, as the ledger requires.
- Migrating the client's custom modules. Staging already covers that.

## Decisions

### 1. `odoo_dwg/intake.py` is pure; git, tar and PostgreSQL stay in `system.py`

The module holds:
- `IntakeRecord`, with `parse_intake` and `dump_intake`;
- `KNOWN_RESTORE_ERRORS`, with `parse_restore_errors(stderr)` and `classify`;
- `SECRET_COLUMNS` and `reader_role_sql(role, database, existing)`;
- `addons_path_dirs(conf_text, archive_root)`;
- `classify_modules(listing, installed)`;
- `git_blob_id(data)`, which computes git's blob hash in Python: `sha1(b"blob %d\0" + data)`;
- `parse_raw_log(text)` and `match_core(...)`.

**Git's blob id is computed in Python, not by `git hash-object`.** That keeps the comparison pure and
testable. It is the same function git uses, so the `verify_intake` tool checks it against
`git hash-object` once.

### 2. `git log --raw` is parsed in Python, with merges included

The first intake parsed `git log --raw` with `awk`. `awk` split on the tab inside each line, which moved
the path into another field, so nothing ever matched. It also missed every version a merge commit
produced.

The system call is:

```text
git log --raw --no-abbrev --no-renames --diff-merges=separate --format=@%H %cs HEAD -- <paths>
```

`parse_raw_log` reads it by splitting on the one tab that separates status from path. It returns
`{(path, blob): first commit date}`. A test feeds it a line from a merge commit, so the merge case cannot
regress.

### 3. Histories are blobless clones, kept apart from the build clones

Build clones are shallow (`--depth 1`) and have no history. Comparing against one reported every
difference as a local patch.

History lives in `.repos/history/{odoo,ocb}-<version>`, cloned with:

```text
git clone --filter=blob:none --no-checkout --single-branch -b <version>
```

Trees and commits are all a comparison needs, because trees carry the blob ids. For the 12.0 branches this
is a few hundred MB, cloned once per host and shared by every environment.

### 4. The core's exact commit is found by tree comparison in a bounded window

The window starts at the newest matched first-commit date among the differing files. It covers the next
90 days of first-parent commits of the matching flavour, and at most 200 of them. For each commit, the
tool reads `git ls-tree -r <commit> -- addons odoo/addons` and compares it with the client's
`{path: blob}`. The commit with the fewest differing entries wins, and zero differences means exact.

The client's own additions are counted but shown apart, because they are not differences in Odoo:
- a file that exists only in the client's copy, such as a stray `.xml_backup`;
- a missing `.pyc`.

### 5. Where the core is in the archive

In the client's `addons_path`, the core shows up as:
- an entry ending in `odoo/addons` that holds `base/__manifest__.py`;
- its sibling `addons` directory.

The archive's directory that contains the `odoo` directory is the core root. If none is found, the
operator is asked. The framework itself (`odoo/*.py`) may be absent from the archive. When it is, the
identification relies on the add-ons trees and says so.

### 6. The source is cloned at a commit, and pinned

The intake record's `core` is `{flavour, url, commit}`. `plan_seed_environment` clones the core into
`.repos/<flavour>-<version>-<commit12>` with:

```text
git init
git fetch --depth 1 <url> <commit>
git checkout FETCH_HEAD
```

GitHub serves any reachable commit by its id. Because the directory name carries the commit, a refresh
never moves it. The venv is built from that clone's `requirements.txt`. The source configuration's
`addons_path` is:
1. every client directory from the record, as absolute paths under `client-src/`;
2. the clone's `addons`;
3. the clone's `odoo/addons`.

`MigrationEnv` gains `intake: IntakeRecord | None`. The workflow loads it, because `models` stays free of
I/O. `source_odoo_bin` and `source_addons_path` consult it.

### 7. The guarded start takes the source version, and the filestore

`render_open_for_testing_sh` adds a case for the source version, using the source's own clone, venv and
configuration. The configuration's `data_dir` is `<env root>/data`.

**Unpacking the filestore** is its own action. It unpacks into `<env root>/data/filestore/<reference>`. It
finds the directory of two-hex-digit buckets whatever the archive's top level is, and refuses a target
that exists.

**A copy needs its own filestore.** Odoo looks up `filestore/<database>`, so a copy opened under another
name would find no attachments. When a copy has none, the start script creates it with `cp -al` from the
reference's: hard links, so the copy takes no extra space. This is safe because Odoo never rewrites an
attachment file in place. Files are content-addressed, written new and unlinked when unused, so a copy
cannot alter the reference's files through a shared inode.

The script refuses the reference database by name, as recorded in `intake.json`.

### 8. The reader role is SQL built from the catalogue, applied as the database owner

`reader_role_sql` does four things:
1. revokes `TEMPORARY` on the database from `PUBLIC`;
2. grants `CONNECT` and schema `USAGE`;
3. grants `SELECT` on every table;
4. for each table holding a secret column that exists, revokes the table grant and grants every other
   column.

Existence is read from `pg_attribute`, never from `information_schema`, which hides columns by privilege.

Role creation and `default_transaction_read_only` need a superuser. They are a separate command, run with
`sudo -u postgres` in the plan, with its own preview line. The password is generated in the workflow,
passed to `psql` on standard input (never in `argv`), and appended to `~/.pgpass` by a command whose
preview shows `<hidden>`.

### 9. Menu and findings

The steps sit under **Migration → Take in a client copy**, each previewed and confirmed:

| Step | Confirmation |
|---|---|
| restore the dump | normal |
| create the reader role | normal |
| unpack the archive | normal |
| classify the archive | normal |
| identify the core | normal |
| unpack the filestore | normal |
| build the source | normal |
| copy the reference to a working database | phrase `COPY` |

Each step:
- writes its data tables to `findings/data/intake-*.tsv`;
- appends findings with ids prefixed `intake-`, starting a ledger first if the environment has none, after
  asking for the client's name;
- updates `intake.json`.

## Risks / Trade-offs

- **History clones need the network and a few hundred MB.** → They are cloned once per host and version,
  and shared. The identification says clearly when a history is missing, rather than guessing.
- **A client on neither official Odoo nor OCB** (another fork) matches neither history. → It is reported
  as "unidentified, N files differ", with the files. The operator can then point the record at the right
  repository by hand.
- **Hard-linked filestores tie a copy to the reference's inodes.** → Odoo never writes an attachment in
  place (decision 7). The verifier checks that writing a new attachment to the copy leaves the reference's
  directory unchanged.
- **The reader role's password lives in `~/.pgpass`.** → It is mode `600` and in the operator's home, like
  any `libpq` credential. It is never printed, never in `argv`, and never in the environment directory.

## Migration Plan

Environments without `intake.json` are untouched. On the reference host:
- the first client's hand-made intake is converted into an `intake.json`, and its findings are already in
  its ledger;
- the steps not yet run are run through the new actions: the filestore, the source build and the guarded
  start.
