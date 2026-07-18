# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through
[GitHub Security Advisories for this repository](https://github.com/grojof/odoo_dev_workspace_generator/security/advisories/new)
— do not open a public issue. You will get an acknowledgement, and a fix or an assessment before any
public disclosure.

## Scope

This tool generates files and runs commands **on your own host, only after showing you the exact plan and
asking for confirmation** (destructive actions require typing an exact phrase). Security-relevant surfaces:

- Shell/SQL command construction from operator input (quoted and validated — see `odoo_dwg/models.py`
  validators and `shlex.quote` usage).
- Downloaded artifacts: wkhtmltopdf installs are SHA-256-pinned and abort on mismatch.
- The PostgreSQL loopback-trust configuration written by `provision apply` is a **development-only**
  convenience, documented as such; do not use it on shared or exposed hosts.

Supported versions: the latest `main`. There are no maintained release branches.
