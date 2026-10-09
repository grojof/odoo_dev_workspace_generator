# Design

## Which cluster is "local"

`pg_lsclusters` lists the clusters of this host's `postgresql-common` layout with their ports, and reads them
without authenticating. A server answering on loopback may belong to another WSL distribution and appears in
no such list. So:

- exactly one local cluster → its port, online or not (a stopped cluster still owns its port);
- several → the one online, when exactly one is;
- none, or no `pg_lsclusters` (PostgreSQL not installed yet) → 5432, PostgreSQL's default.

The models stay pure: the port is read in `system.py` and passed in by the workflows, which already build
`WorkspaceConfig` and `MigrationEnv` there.

## Apply's connection check

When apply plans PostgreSQL the cluster may not exist yet, so the port cannot be known at planning time. The
step reads it at run time from the server the role was created in — `sudo -u postgres psql -XtAc 'SHOW
port'` goes through the same `pg_wrapper` choice as the role creation — and connects there. Asking the server
it configured is what makes the check unable to pass against someone else's.

## Not changed

- A profile or environment that states a port keeps it.
- Odoo's HTTP ports can also collide across distributions, but a collision there fails loudly (`Address
  already in use`), while a database port that reaches another server works and is wrong.
