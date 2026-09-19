## ADDED Requirements

### Requirement: Egress control and mail capture readiness

`provision check` SHALL report, without changing anything:
- whether OpenSnitch is installed and its service is running, with its configured default action and
  process-monitor method, flagging any value that differs from the hardened configuration;
- whether Mailpit is installed and listening on `127.0.0.1:1025`.

Both SHALL be reported as optional.

#### Scenario: Softened configuration is flagged

- **WHEN** OpenSnitch runs with `DefaultAction` set to `allow`
- **THEN** the check reports the setting and that it differs from the hardened `deny`
