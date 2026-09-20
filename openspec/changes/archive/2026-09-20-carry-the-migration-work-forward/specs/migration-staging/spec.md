# migration-staging Specification Delta

## ADDED Requirements

### Requirement: Reviewed module code is promoted to a location the operator owns

The staged code of a module at a step is the operator's own work — the migrator's mechanical output plus
every correction made by hand — and it lives inside the migration environment, which cleaning removes and
re-staging replaces. The system SHALL offer an action that **promotes** a module's reviewed code for one or
more steps to a durable location the operator names: one directory per version, outside any migration
environment.

Promotion SHALL **copy**, never move: the environment stays runnable, and a promotion can be discarded and
made again. It SHALL go through the standard plan → preview → apply flow, and SHALL require an exact-phrase
confirmation when it would replace code already promoted for that module and version, since that code may
carry review the environment's copy does not.

Where the durable location is a git repository, the system SHALL offer to commit the promotion on the branch
that names the version, using the **operator's** identity, hooks and signing configuration — it is their
history. This is the opposite of the throwaway repositories staging creates inside each stage directory,
which are deliberately insulated from that configuration, and the generated documentation SHALL say which is
which.

#### Scenario: A reviewed step is promoted

- **WHEN** the operator promotes `client_sales` for step 16.0
- **THEN** the module's 16.0 staged code is copied to the durable location's `16.0` directory, and the
  environment's copy is unchanged

#### Scenario: Replacing promoted code is confirmed first

- **WHEN** the operator promotes a module and version that has been promoted before
- **THEN** the action names that module and version, and promotes nothing unless the exact phrase is typed

### Requirement: Staging consumes what has been promoted

A migration is rehearsed several times and run once, and the final run must apply what was proven rather
than derive it again. For each module and step, staging SHALL take its input from the durable location when
that module has promoted code for that version, and SHALL derive from the previous step only when it has
none.

A step whose input was promoted SHALL NOT run the module migrator: the code is already at that version. The
staging report SHALL state, for every step, whether it was derived or taken from the promoted copy, because
a step that was not derived is a step whose warnings the operator will not see this run.

A chain with nothing promoted SHALL behave exactly as it does without this capability.

#### Scenario: The final run applies proven work

- **WHEN** every step of a module has been promoted and the operator stages it again
- **THEN** no migrator runs for that module, each step's code comes from the durable location, and the
  report says so per step

#### Scenario: A partly promoted module is completed

- **WHEN** a module has promoted code up to 16.0 and nothing beyond it
- **THEN** steps up to 16.0 are taken from the durable location and 17.0 onward are derived from them

### Requirement: Divergence between the environment and the promoted copy is reported

Promotion copies, so the two can drift: the operator keeps working in the environment, or edits the durable
copy directly. The staging report SHALL name, per module and version, whether the environment's code and the
promoted code differ, comparing **content** rather than timestamps — a `cp -a` and a `git checkout` both
preserve times that say nothing about content.

Neither copy SHALL be treated as authoritative: the report says they differ and names both paths, and the
operator decides.

#### Scenario: Work continued after a promotion

- **WHEN** a module is promoted for 16.0 and then edited again in the environment
- **THEN** the report names that module and version as diverged, and says which path holds which copy
