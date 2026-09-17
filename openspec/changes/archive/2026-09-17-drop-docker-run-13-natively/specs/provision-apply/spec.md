# Spec Delta

## REMOVED Requirements

### Requirement: Optional Docker Engine install

**Reason**: The Odoo 13 step runs natively now, so no migration needs a container runtime. Offering to
install one would install something the tool never uses.

**Migration**: A host that accepted this option in an earlier version keeps Docker installed and unused;
remove it with the distribution's package manager if it is not wanted for other purposes.

### Requirement: Optional OpenUpgrade fallback image pull

**Reason**: The `odoo:13.0` / `odoo:12.0` images backed the container step, which no longer exists.

**Migration**: Images already pulled can be removed with `docker image rm odoo:13.0 odoo:12.0`; nothing in the
tool refers to them.
