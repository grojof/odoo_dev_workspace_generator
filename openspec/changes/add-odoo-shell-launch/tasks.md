# Tasks

## 1. Implementation

- [ ] 1.1 Emit an Odoo shell configuration per version and a shared `odooDatabase` input in `launch.json`;
      unit tests for the pair per version, the arguments and the input
- [ ] 1.2 Mention both configurations in the generated README
- [ ] 1.3 Run the shell in `tools/verify_workspace_versions.py`, piping an ORM query and requiring its answer

## 2. Docs

- [ ] 2.1 Update `docs/workspace-layout.md` and `CHANGELOG.md`

## 3. Acceptance

- [ ] 3.1 Project checks green: pytest, ruff, `openspec validate --specs`, CLI smoke
- [ ] 3.2 Run `tools/verify_workspace_versions.py` on this host: every version from 12.0 to 19.0 passes, the
      shell included
