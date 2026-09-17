# Spec Delta

## REMOVED Requirements

### Requirement: Chain-scoped host readiness check

**Reason**: The requirement's substance was that Docker checks appear only for chains with an Odoo 12/13 step,
and its scenarios asserted exactly that. With every step native, no chain needs a container runtime and those
scenarios describe behaviour that no longer exists.

**Migration**: Replaced by "Host readiness for a native chain" below. The PostgreSQL and `uv` checks are
unchanged; only the Docker ones are gone.

## ADDED Requirements

### Requirement: Host readiness for a native chain

The system SHALL provide a read-only migration preflight that verifies the host tools every chain needs:
`uv`, PostgreSQL reachability, and the development role. Because every step runs natively, no chain requires
a container runtime and the preflight SHALL NOT check for one. The result SHALL be rendered as a capability
table (check, state, detail) with states OK / WARN / MISSING / INFO, and the check MUST NOT modify the host.

#### Scenario: The same tools are checked for every chain

- **WHEN** the preflight runs for a 14 → 18 chain and for a 12 → 19 chain
- **THEN** both report `uv` and PostgreSQL, and neither reports a container runtime

#### Scenario: A missing interpreter provider is reported

- **WHEN** `uv` is absent from the host
- **THEN** the report marks it MISSING, because no step can be built without it

#### Scenario: The check changes nothing

- **WHEN** the preflight runs against a host missing every prerequisite
- **THEN** it reports them and makes no change to the host
