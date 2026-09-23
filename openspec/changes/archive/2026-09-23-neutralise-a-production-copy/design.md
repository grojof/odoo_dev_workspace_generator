# Design

## Context

- **Mail capture already solves this shape for one path.** It works through the SQL built in `egress.py`
  (`mail_capture_sql`, `mail_restore_sql`) and keeps a record table inside the database
  (`odwg_mail_capture`) that survives every dump, restore and chain step. It rests on
  `jsonb_populate_record` to write back values without knowing their column types.
- **Odoo's own `neutralize` is one-way.** It exists from 16.0 (`odoo/modules/neutralize.py`) and is
  spread across one `data/neutralize.sql` per module:
  - 40 files in 16.0 and 77 in 19.0 (local clones, `~/odoo-migrations/.repos/odoo-<v>`);
  - it deletes push devices;
  - it replaces `database.secret` with `dummysecret`;
  - it rewrites IAP tokens;
  - it keeps no record.
- **The OCA Spanish SII keeps the same company fields across the rename.** They are checked in the
  sources:

  | Branch | Module | Fields |
  |---|---|---|
  | `OCA/l10n-spain` 12.0 | `l10n_es_aeat_sii` | `res_company.py:15-16`: `sii_enabled`, `sii_test` |
  | 13.0 and 18.0 | `l10n_es_aeat_sii_oca` | `res_company.py:17-18`: the same `sii_enabled` and `sii_test` |

## Goals / Non-Goals

**Goals:**
- One catalogue that is correct on every version from 12.0 to 18.0, because each rule is guarded by the
  existence of what it touches.
- Reversible to the exact value, with the record in the database it describes.
- Repeatable: the driver re-applies it after every step, and a re-apply records only what is new.

**Non-Goals:**
- Blocking the network. That is the outbound firewall's job, and it stays under this as the net.
- Deleting anything. Odoo deletes push devices and subscriptions; we leave them, because with crons off,
  mail captured and IAP disabled nothing sends to them.
- Country EDIs other than Spain's in the first catalogue. The source verifier (decision 8) lists every
  official `neutralize.sql` the catalogue does not cover yet, so the gap is visible, not silent.

## Decisions

### 1. A rule is data: table, predicate, column → neutral value

`odoo_dwg/neutralise.py` declares:

```python
Rule(id, source, table, where, sets: dict[column, sql_expr], requires: tuple[column, ...])
```

- `source` is the rule's evidence string. Examples: `"odoo 16.0–19.0 addons/delivery/data/neutralize.sql"`,
  `"OCA/l10n-spain 12.0 l10n_es_aeat_sii/models/res_company.py:15-16"`.
- The catalogue is a tuple of these.
- Special cases are rules too:
  - crons: `where = active AND id NOT IN (allowlisted xmlids)`;
  - queued jobs: `where = state IN (...)`, `sets = {state: 'failed'}`;
  - the IAP token: `sets = {account_token: account_token || '+disabled'}`.
- One kind is an **insert**: `database.is_neutralized`, when absent, is inserted and recorded as
  inserted, so restoring deletes it.

**Alternative:** hand-written SQL per rule. It was rejected because a generic renderer is what makes the
record, the idempotence and the restore uniform, and testable once.

### 2. The SQL: one guarded block per rule, record before write

For each rule the renderer emits a `DO` block that:

1. **Checks the rule applies.** It checks `information_schema.columns` for the table and every column in
   `requires` and `sets`. If one is missing, it records the rule as `not applicable` in the run table and
   moves on.
2. **Records before it writes.** For each row matching `where` whose column value `IS DISTINCT FROM` the
   neutral value, and which has **no record yet** for that `(table, row id, column)`, it inserts the
   record with `to_jsonb(<column>)` as the original. The xmlid comes from `ir_model_data` where one
   exists.
3. **Writes.** It updates those rows.

Because records are never overwritten, the original production value is always the first one recorded.
Re-applying after a step records only new rows or new columns.

**Existence is read from `pg_attribute`, never from `information_schema.columns`.** The latter lists
only the columns the connected role may read. The first check against a real client copy was run as a
read-only role that hides secret columns, and it took `ir_config_parameter.value` and
`iap_account.account_token` for absent columns. It silently skipped their rules and reported an armed
database as nearly clean. Read from the catalogue, the column exists, the rule is checked, and such a role
gets a permission error: "could not tell" (exit 2), never a partial verdict.

**Restore** writes each recorded value back with
`(jsonb_populate_record(NULL::<table>, jsonb_build_object(<col>, original))).<col>`, the same technique as
the mail capture, so no column type is spelled out.

### 3. Two tables, and "production" is the first run

| Table | Holds |
|---|---|
| `odwg_neutralisation_run` | `run`, when, and the `base` module's `latest_version` at that time |
| `odwg_neutralisation` | `run`, rule, table, row id, xmlid, column, original, applied, kind (`update` or `insert`), when |

Run 1 is the source database: what production was. A record made by a later run is a row that did not
exist in production, typically a cron a migration step created. Restore gives back run 1's records and
**names** the others as left neutralised. The same holds for a later-run record of a row that did exist
in production but that an older catalogue did not cover. That misclassification errs on the side of
staying off. The operator sees the list and decides.

### 4. The allowlist is small and cited

Only housekeeping that sends nothing stays active:
- `base.autovacuum_job`: Odoo's own neutralisation keeps exactly this one (`base/data/neutralize.sql`,
  16.0–19.0);
- `queue_job`'s done-job autovacuum, which deletes old done jobs and calls nothing.

Each entry names why it is safe. The allowlist is matched by external identifier, never by name. Cron
names are translated and edited, and a name match would keep the wrong cron alive.

### 5. Mail is composed, not re-done

The neutralise plan runs the mail capture's SQL first and its own after it. The restore plan runs its own
first and the mail restore after it. The mail capture keeps its own record, check and restore. The
neutralise check reports the mail verdict by calling the mail capture's state reader.

### 6. The local URL is asked, with the environment's default

`web.base.url` is set to a URL the action asks for:
- defaulting to the workspace's or migration step's `http://127.0.0.1:<port>`;
- given to the driver from the step's conf.

`web.base.url.freeze` is set to `False` and recorded. `database.uuid` is set from `gen_random_uuid()`
where it exists (PostgreSQL ≥ 13), else from an `md5(random()…)` formatted as a UUID, since 12.0 copies may
be restored on older servers too.

### 7. The driver runs the same SQL, from a file the plan wrote

Generating the migration environment writes `neutralise.sql` beside `run_migration.sh`, rendered from the
same catalogue. The driver runs it with `psql -X -v ON_ERROR_STOP=1`:
- after the source restore;
- after each successful step, before `pg_dump`;
- after a checkpoint restore.

A failure stops the run. The driver has **no** restore path. The generated-shell verifier and the
migration-driver verifier (stub `psql`) cover the calls and their order.

### 7b. Neutralisation does not last, so every start re-applies it

Odoo switches crons back on by itself:
- **a module update** rewrites every cron its data does not mark `noupdate`. Counted in the local clones:
  31 of 31 cron records in 12.0 and 85 of 93 in 18.0 are updatable. Of those, 5 and 19 declare `active`
  explicitly;
- **an install or reinstall** creates crons active;
- **OpenUpgrade** loads `noupdate_changes.xml` per step.

So a neutralised database is only neutralised until the next install or update. The environment's
`open_for_testing.sh` covers both sides:
- **across sessions:** it re-neutralises and checks on every start, and refuses to start when anything
  can still act;
- **within a session:** it starts `odoo-bin` with `max_cron_threads = 0`, so a cron created or reactivated
  by an install from the interface cannot run before the next start re-neutralises it.

Queued jobs need no extra guard here. The tool's confs never load `queue_job` as a server-wide module, so
no job runner starts.

**Alternative:** an Odoo add-on that re-neutralises on every module install. It was rejected because it
would be code of ours running inside the client's database, and it would need to survive the migration
itself. A start-time guard and zero cron threads get the same result from outside.

Workspaces that open client copies (`max_cron_threads = 1` today) are out of this change's scope. The
roadmap notes them as the next place the same guard belongs.

### 8. Sources are re-verified, not remembered

`tools/verify_neutralise_sources.py` reads the local Odoo clones 16.0–19.0. It lists every
`data/neutralize.sql`, and for each one prints the catalogue rules that cite it or `not covered`. It also
checks that every table and column a rule cites from an Odoo file actually appears in that file.

The OCA rule cites file and line. The verifier greps them in the cached OCA trees when present. It is a
host-side tool, like the other `verify_*`, and is not in the test suite.

### 9. Surface

| Where | Action |
|---|---|
| Workspace and Migration menus, beside mail capture | **Neutralise a database** (previewed, confirmed; phrase `NEUTRALISE`) |
| Workspace and Migration menus, beside mail capture | **Give a neutralised database its production settings back** (previewed; phrase `RESTORE PRODUCTION`) |
| Command line | `odoo-dwg neutralise check --database X [--db-host --db-port --db-user]`: read-only, exit 0/1/2 |

## Risks / Trade-offs

- **A rule that matches too broadly turns off something harmless.** → Nothing is deleted and everything
  is recorded, so the cost is a restore, not a loss. Rules follow Odoo's own predicates where Odoo has
  them.
- **A rule that matches too narrowly leaves something armed.** → The check reports by rule, and the
  outbound firewall still denies by default. The host-side acceptance starts each version on a
  neutralised copy and reads the firewall journal.
- **Holding queued jobs as `failed` makes them look failed in the UI.** → They are recorded and restored
  exactly. The check names them. The alternative, deleting them, is not reversible.
- **A migration can rename a table or column between the record and the restore.** → Restore reports
  every record it cannot apply, by rule, table and column, and changes nothing for those.

## Migration Plan

This lands with no effect on existing databases until an action or the driver runs it. Environments
generated before it have no `neutralise.sql`. Regenerating adds it, and the driver prints a warning, not
a failure, when the file is absent. An operator can then run the menu action by hand.
