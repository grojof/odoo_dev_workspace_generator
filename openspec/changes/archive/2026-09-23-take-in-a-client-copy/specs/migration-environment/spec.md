# Spec Delta

## ADDED Requirements

### Requirement: The source version is what the client runs

When the environment has an intake record, the source version SHALL be built from what the intake
identified, not from official Odoo at the branch head:

- **Core:** the core is cloned from the identified repository (official Odoo or OCA/OCB) at the
  identified commit.
- **Add-ons path:** the client's own add-on directories under `client-src/`, in the order of the client's
  `addons_path`, followed by the core's add-ons.
- **Staying fixed:** the clone SHALL be checked out at that commit and SHALL NOT follow the branch. A later
  refresh SHALL NOT move it.
- **Python dependencies:** the source's virtualenv SHALL also get the Python dependencies the intake
  recorded for the installed modules. They are installed on every build, since installing what is already
  satisfied changes nothing, so a dependency recorded after the venv was built is not missed.

The chain's steps are unaffected. From 13.0 they run OpenUpgrade and the target versions, as before.

#### Scenario: A client on OCB

- **WHEN** the intake identified OCA/OCB 12.0 at a commit, and the client's `addons_path` lists fifty
  directories
- **THEN** the source clone is OCB at that commit, and the source configuration's `addons_path` is those
  fifty directories under `client-src/`, in the client's order, then the core's add-ons

#### Scenario: No intake

- **WHEN** the environment has no intake record
- **THEN** the source version is official Odoo at the branch head, as before
