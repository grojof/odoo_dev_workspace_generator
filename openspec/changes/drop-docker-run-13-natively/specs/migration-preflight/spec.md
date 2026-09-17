# Spec Delta

## MODIFIED Requirements

### Requirement: Chain-scoped host readiness check

The system SHALL provide a read-only migration preflight that verifies the host tools required by the
*specific* chain: `uv` always, plus PostgreSQL reachability and the development role. Because every step now
runs natively, no chain requires a container runtime and the preflight SHALL NOT check for one. The result
SHALL be rendered as a capability table (check, state, detail) with states OK / WARN / MISSING / INFO, and
the check MUST NOT modify the host.

#### Scenario: The same tools are checked for every chain

- **WHEN** the preflight runs for a 14 → 18 chain and for a 12 → 19 chain
- **THEN** both report `uv` and PostgreSQL, and neither reports a container runtime

#### Scenario: A missing interpreter provider is reported

- **WHEN** `uv` is absent from the host
- **THEN** the report marks it MISSING, because no step can be built without it
