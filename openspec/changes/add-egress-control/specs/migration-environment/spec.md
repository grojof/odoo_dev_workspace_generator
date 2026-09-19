## ADDED Requirements

### Requirement: Migration steps send mail to the local capture

Each migration step's generated `odoo.conf` SHALL set `smtp_server = 127.0.0.1` and `smtp_port = 1025`.

#### Scenario: SMTP keys in a step config

- **WHEN** the step config for `17.0` is rendered
- **THEN** it contains `smtp_server = 127.0.0.1` and `smtp_port = 1025`
