# Spec Delta

## MODIFIED Requirements

### Requirement: A migrated database is opened for testing only through a guarded start

The migration environment SHALL include a script that starts Odoo on a chosen database of that
environment. The version SHALL be the chain's **source** version or one of its steps. The database SHALL
be either:
- a copy of the client's reference;
- the working database;
- a database restored from a checkpoint.

Opening any of them for testing SHALL go through this script, which on every start:

1. **Re-neutralises** the database, which covers what an install, update or migration step switched back
   on since the last start.
2. **Runs the check.** If anything can still act on the outside, it refuses to start, naming what can act.
3. **Starts Odoo with cron threads at zero**, listening on loopback only, with the version's add-ons and
   the mail sent to the local capture. A cron that a module installed during this session creates, or
   switches on, cannot run until the next start neutralises it.

For the source version, the script SHALL use the source's own clone, virtualenv and configuration, which
come from the intake when there is one. It SHALL use the environment's data directory, so that an unpacked
client filestore is found.

The script SHALL NOT restore production settings, and SHALL offer no option that skips the
re-neutralisation or the check. It SHALL refuse the reference database itself, which nothing modifies.

#### Scenario: A module installed while testing

- **WHEN** the operator installs a module from the interface of a migrated database opened through the
  script, and that module creates an active cron
- **THEN** the cron does not run during that session, and the next start through the script turns it off
  and records it

#### Scenario: A database that cannot be neutralised

- **WHEN** the script is pointed at a database where the check still finds something that can act after
  re-neutralising
- **THEN** it does not start Odoo, and names what can act

#### Scenario: The client's source instance

- **WHEN** the script is run with the source version on a neutralised copy of the client's reference
- **THEN** it starts the source Odoo the intake identified, with the client's add-ons, with no cron thread

#### Scenario: The reference is refused

- **WHEN** the script is pointed at the reference database
- **THEN** it refuses to start, saying that the reference is never modified and a copy should be opened
  instead
