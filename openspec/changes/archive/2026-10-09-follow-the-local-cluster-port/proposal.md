# Follow the local PostgreSQL cluster's port

## Why

WSL 2 distributions share one network namespace: `127.0.0.1:5432` in one distribution is the PostgreSQL of
another when that one already holds the port. Ubuntu's `pg_createcluster` then gives the new cluster the next
free port (5433). Rehearsing the setup guide on a fresh distribution beside an existing one showed:

- **`provision check`** reported the new, running cluster as "installed but not running": it asks
  `pg_lsclusters` for a cluster on 5432 only.
- **`provision apply`**'s final step, "Check that odoo connects over loopback", passed against the *other*
  distribution's server: its `psql -h 127.0.0.1` names no port.
- **A new workspace or migration environment** is written with `db_port = 5432`, so its databases would be
  created in the other distribution's server — one holding unrelated, possibly client, databases — through a
  role that server trusts on loopback.
- **The read-only commands** (`migrate audit`, `migrate modules`, `mail check`, `neutralise check`) default
  `--db-port` to 5432, so they can read a same-named database on the other server.

## What changes

- The port of the host's own cluster, read from `pg_lsclusters` without authenticating, is what the check
  probes and what new workspaces, migration environments and the read-only commands default to. 5432 remains
  the fallback when no single local cluster can be told.
- Apply's connection check asks the server it just configured for its port (`SHOW port`, through the same
  `sudo -u postgres psql` that created the role) and connects there.
- The workspace README's `createdb` line names the port.

## Impact

- `odoo_dwg/system.py`, `provisioning.py`, `planners.py`, `templates.py`, `cli.py`,
  `workflows/{workspace,migration,checks,common}.py`.
- A workspace or environment already written keeps the port in its profile or configs: nothing existing moves.
