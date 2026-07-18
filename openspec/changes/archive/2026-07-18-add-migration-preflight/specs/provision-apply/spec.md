# provision-apply Specification (delta)

## ADDED Requirements

### Requirement: Optional Docker Engine install

`provision apply` SHALL offer, as an optional step, installing Docker Engine from the distro archive
(`docker.io` on the apt family) and enabling its service — needed only when a migration chain includes an
Odoo 12/13 step. A host that does not need Docker MUST NOT have it installed.

#### Scenario: Docker install is opt-in

- **WHEN** the user declines the Docker option
- **THEN** no Docker install command is included in the plan

### Requirement: Optional OpenUpgrade fallback image pull

`provision apply` SHALL offer, as an optional step, pulling the OpenUpgrade fallback images
(`odoo:13.0`, `odoo:12.0`) so the Docker step of a migration does not fail at run time on a missing image.
The pull SHALL be part of the previewed plan like every other host-mutating command.

#### Scenario: Images are pulled through the plan

- **WHEN** the user opts into the image pull
- **THEN** the previewed plan contains the `docker pull` commands and they run only after confirmation
