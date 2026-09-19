## MODIFIED Requirements

### Requirement: Install the Odoo-recommended patched wkhtmltopdf verified by checksum

`provision apply` SHALL install the Odoo-recommended patched wkhtmltopdf 0.12.6 (the build Odoo recommends
from 15 on), downloading the pinned asset for the host codename and verifying its SHA-256 before installing.
A checksum mismatch MUST abort the install. 0.12.5, recommended for Odoo ≤ 14, is not provisioned. When no
verified asset is pinned for the host, apply SHALL say so instead of skipping it silently.

#### Scenario: Checksum mismatch aborts

- **WHEN** the downloaded wkhtmltopdf asset does not match its pinned SHA-256
- **THEN** the install step aborts and wkhtmltopdf is not installed

#### Scenario: Version follows the Odoo rule

- **WHEN** provisioning for Odoo 18 (≥ 15)
- **THEN** the planned wkhtmltopdf is the 0.12.6 patched build
