## MODIFIED Requirements

### Requirement: Checkpoint after each step and resume on failure

The driver SHALL `pg_dump` the working database after each successful step and, on a failed step, stop and
leave the last good checkpoint intact so a re-run resumes from it rather than restarting from the source.

On a re-run the driver SHALL restore the newest checkpoint into the working database before the first
pending step. A failed step can leave the database half-migrated, because OpenUpgrade commits module by
module, and that state must never be migrated again.

The driver SHALL record the SHA-256 of the source dump with the first checkpoint, and SHALL refuse to resume
with a different dump.

#### Scenario: Re-run resumes from the last good checkpoint

- **WHEN** step 5 of a chain fails after steps 1–4 succeeded
- **THEN** checkpoints for steps 1–4 remain and re-running the driver resumes at step 5, not at the source

#### Scenario: The half-migrated database is replaced before resuming

- **WHEN** step 16.0 failed after checkpoints for the source and 15.0 were written
- **THEN** the re-run restores the 15.0 checkpoint into the working database and only then runs step 16.0

#### Scenario: A different source dump is refused

- **WHEN** the driver is re-run with a dump whose SHA-256 differs from the one its checkpoints came from
- **THEN** it stops before touching the database and says the checkpoints belong to another dump
