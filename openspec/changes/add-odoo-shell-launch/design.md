## Context

`odoo-bin shell` is Odoo's own subcommand in every supported version, 12 to 19 (`odoo/cli/shell.py`). It takes
the same `-c`, needs `-d` to build an `env`, and falls back to the plain Python REPL unless `shell_interface`
names an installed alternative.

## Decisions

- **One shell configuration per version, beside the server one**, named `Odoo <version> shell (<instance>)`,
  so the picker lists them in pairs.
- **Ask for the database at launch** with a `promptString` input (`odooDatabase`, default the workspace name).
  *Alternative:* fix `-d` in `odoo.conf` — rejected, because it would also pin the server to one database.
- **`console: integratedTerminal`** is required: the REPL needs a real terminal for its input.
- **Verified by piping a script into the shell**, which is how a non-interactive check exercises the same
  command the configuration runs. The script counts `res.users`.

## Risks / Trade-offs

- VS Code remembers nothing between prompts, so the database name is typed on every start. → The default
  covers the common case of one database per workspace; the input can be changed to `pickString` later if
  needed.
