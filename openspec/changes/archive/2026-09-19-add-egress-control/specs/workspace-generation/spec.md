## ADDED Requirements

### Requirement: Workspace mail goes to the local capture

Each generated workspace `odoo.conf` SHALL set `smtp_server = 127.0.0.1` and `smtp_port = 1025`, so that mail
sent through the configuration server reaches the local capture when it runs and is refused when it does
not. It is never delivered elsewhere.

#### Scenario: SMTP keys in odoo.conf

- **WHEN** `config/odoo18.conf` is rendered
- **THEN** it contains `smtp_server = 127.0.0.1` and `smtp_port = 1025`
