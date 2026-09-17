# Spec Delta

## REMOVED Requirements

### Requirement: Debian/Ubuntu family only

**Reason**: The supported host is now the explicit release list the support matrix declares (Ubuntu 22.04 and
24.04), not the apt package family. Accepting any apt-family host implied validated support for Debian, which
never happened, and let `apply` run privileged installs on a host the project makes no claim about.

**Migration**: Replaced by "Supported Ubuntu releases only" below. An operator on Debian or another
apt-family host that `apply` previously accepted is now refused before any command runs; provisioning such a
host has to be done by hand, following `docs/provisioning.md` as a reference for what the plan would install.

## ADDED Requirements

### Requirement: Supported Ubuntu releases only

`provision apply` SHALL target only the host releases the support matrix declares. On any other host —
including an apt-family host that is not one of those releases — it MUST refuse cleanly, naming the detected
release and the supported ones, before assembling or running any command.

#### Scenario: A supported release proceeds to the plan

- **WHEN** `provision apply` runs on one of the Ubuntu releases the matrix declares
- **THEN** it assembles and previews the plan as usual

#### Scenario: An unsupported host is refused before any command

- **WHEN** `provision apply` runs on a host that is not one of the declared releases
- **THEN** it refuses with a message naming the detected release and the supported ones, and makes no changes
