## Context

Two independent reviews ran before 0.2.0: documentation against code, and code correctness and security. Each
finding was re-checked by hand before it was accepted. For example, `MigrationEnv(source="13.0$(touch /tmp/x)")`
validated, and so did a `WorkspaceConfig` whose version was `18.0$(touch /tmp/p)`. Of the driver's checkpoint
logic, only the skip was implemented, never the restore.

## Decisions

- **Validate at the model; quote in the output.** Every externally supplied value is refused at the model
  (`version_error`, `OCA_REPO_RE`, `DB_HOST_RE`, port ranges, `python_version_error`), including for profiles
  loaded to manage a workspace. The generated scripts also `shlex.quote` every path, so a future field that
  skipped validation would still be inert text. `normalize_defaults` never raises on a bad value; `validate`
  reports it.
- **Versions are the chain's own strings.** `NN.0`, from 12.0 to 19.0, exactly; `18` is refused. That also
  removes the duplicate `18`/`18.0` instance.
- **Resume = restore the newest checkpoint.**
  - Checkpoints are sequential, so the newest is the last contiguous one from `00_source`.
  - It is restored before the first pending step. A fully migrated run restores nothing.
  - The source dump's SHA-256 is stored beside the checkpoints, and a mismatch is refused. Computing it costs
    one read of the dump per run, which is accepted for the safety.
- **One definition of where a step finds modules.** `MigrationEnv.coverage_dirs` and `apriori_file` are
  consumed by both the interactive preflight and the driver. For ≤ 13, the fork's `odoo/addons` is included,
  because `odoo-bin` adds its own core, and the fork's `apriori.py` lives in `openupgrade_records/lib/`. Both
  were checked against the 13.0 fork on disk.
- **The interpreter is read back, not recorded.** A ready migration venv is rebuilt when `pyvenv.cfg` names
  another `3.N` than the step now resolves to. An unreadable `pyvenv.cfg` keeps it, so behaviour is unchanged
  for an environment that cannot be read.
- **Probes that cannot prompt.**
  - `pg_lsclusters` (postgresql-common) gives state and version without authenticating, with `pg_isready` as
    fallback.
  - A role is proven by logging in as it over loopback (`-w`), else asked through `sudo -n`.
  - "Cannot tell" is `None`, and is shown as WARN.
- **`policy-rc.d`.** It is removed by `trap … EXIT INT TERM HUP`, and a leftover carrying the tool's mark is
  reused. Measured under dash: success, failure, SIGINT, own leftover and foreign file all behave.
- **Structure.**
  - `Command` is plain data and moves to `models`, so pure planners no longer import `system`, which re-exports
    it.
  - The redirect action and the apply helper move to `workflows/common.py`, so no workflow imports another.
  - The apt simulation becomes a `system` probe.
- **Removed:** `addon_prefix` (set, never read), `SUPPORTED_DEV_VERSIONS`, `MigrationEnv.is_native` (always
  true) with its branch, and the unused prompt and system helpers.
- **Backups** are stamped with the workflow's clock and passed into the pure planner.

## Risks / Trade-offs

- **A stricter profile can refuse one that loaded before**, for example one with `"18"`. → Reported with the
  field name; the CHANGELOG marks it BREAKING.
- **Hashing a large dump adds seconds to each run.** → Accepted; it prevents resuming onto the wrong data.
