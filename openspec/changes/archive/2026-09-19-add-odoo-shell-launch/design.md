## Context

Everything used is Odoo's own CLI in every supported version, 12 to 19:
- `odoo-bin shell` (`odoo/cli/shell.py`) takes the same `-c` and needs `-d` to build an `env`.
- `--test-enable` and `--test-tags` with the `/<module>` selector are documented in `odoo/tools/config.py`,
  e.g. "`--test-tags :TestClass.test_func,/test_module,external`".

## Decisions

- **Four configurations per version**: server, shell, upgrade modules, test module. They are named
  `Odoo <version> <kind> (<instance>)`, so the picker groups them by version.
- **Ask at launch, not in `odoo.conf`.** A `db_name` in the configuration would pin the server to one database.
  `launch.json` `inputs` of type `promptString` ask when the configuration starts:
  - `odooDatabase`, which defaults to the workspace name;
  - `odooModules` and `odooTestModule`.
- **Tests select by module with `--test-tags /<module>`**, so only that module's tests run rather than those of
  every module loaded. `--stop-after-init` returns control when they finish.
- **The upgrade configuration keeps serving**, because that is what comes next after an upgrade in
  development.
- **Verification runs the generated file itself.** The verifier reads `launch.json`, substitutes the prompts
  and runs each configuration. A change to the generator is then checked as it will be used, not as a copy of
  its arguments.
- **Not included:**
  - *Auto-reload*: `reload` re-executes the process, which detaches the debugger, and it needs `watchdog`,
    which Odoo does not require.
  - *Attach, `scaffold` and the other subcommands*: rarely debugged, and each adds an entry per version.

## Risks / Trade-offs

- The picker holds four entries per version. That is fine for the usual one or two versions, and long for
  all eight. → Accepted; the names group them by version.
- VS Code does not remember prompt answers. → The database default covers the usual case of one database per
  workspace.
