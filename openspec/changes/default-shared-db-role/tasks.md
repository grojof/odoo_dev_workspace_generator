# Tasks

## 1. Shared default role

- [ ] 1.1 Declare `DEFAULT_DB_ROLE = "odoo"` and `DB_ROLE_RE` in `models.py`; make
      `normalize_defaults` fill `db_user` with it and `MigrationEnv` use it; verify a minimal profile resolves
      to `odoo` and an explicit `db_user` is kept
- [ ] 1.2 Read the constant in `provisioning.py` and the `provision apply` prompt instead of the literal

## 2. Validation

- [ ] 2.1 Reject an invalid `db_user` in `WorkspaceConfig.validate`, naming the field; verify with a unit test
- [ ] 2.2 Reject an invalid role in `provision apply` before gathering facts or assembling a plan; cover the
      validator with a unit test

## 3. Docs

- [ ] 3.1 Update `docs/configuration-reference.md`, `docs/workspace-layout.md` and `docs/provisioning.md`:
      the shared role, why it is shared, and that the database selector lists every development database
- [ ] 3.2 Update `CHANGELOG.md` `[Unreleased]` and remove the role caveat from `docs/roadmap.md`

## 4. Acceptance

- [ ] 4.1 Run the project checks green: `python -m pytest -q`, `python -m ruff check .`,
      `openspec validate --specs`, `python -m odoo_dwg --help`
- [ ] 4.2 On this host, generate a workspace with a minimal profile and serve it: `/web/login` answers
      through the `odoo` role with no role created for the workspace; then remove the test workspace and its
      database
