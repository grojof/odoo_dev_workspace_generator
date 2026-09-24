# Design

## Context

Everything these steps need already exists, except the steps themselves:
- `neutralise.check_sql` / `read_armed`, run by `workflows.common.armed_state`, report what a database can
  act on, rule by rule. The mail state comes from `egress`.
- `preflight.chain_fates(modules, steps)` follows a module through each step's `apriori.py`.
  `MigrationEnv.apriori_file(version)` locates the file.
- The intake records `addons_dirs`, `core_dir` and, per installed module, where it loads from
  (`intake-installed.tsv`), and the repository state per directory (`intake-repos.tsv`, remote
  included).
- The first client's hand-made availability check cached blobless trees under `.repos/oca-trees/`.

## Decisions

### 1. Severity lives on the rule

`Rule` gains `severity`. The survey copies it into the finding. It does not rank anything itself: one
place says how serious an armed tax integration is, and the neutralise check and the survey both read
it. A unit test pins the table in the spec, so a rule added later without a severity fails the test.

### 2. The survey reads the reference as its owner

The survey reads the reference with the environment's role, the owner, as the neutralise check already
does, never with the read-only role. That role cannot see `ir_config_parameter.value` or IAP tokens, and
the first check run with it skipped those rules in silence.

Extra facts are read with plain `SELECT`s, each guarded by `to_regclass` and existing columns:
- crons, with `now() - nextcall`;
- `queue_job` by channel and state;
- `mail_mail` by state, with the first and last date.

### 3. Origin comes from the recorded remote

A module's origin is:
- **Odoo** if it loads from the core directories;
- **OCA** if its directory's recorded remote is `github.com/OCA/<repo>`;
- **custom** otherwise, including a third party's repository.

This avoids a second classification: `intake-repos.tsv` already carries the remote, credentials stripped.

### 4. Availability: the client's repositories first, then all of OCA, only where needed

For each step, the set of module names found there is built from:
- the step's core: `openupgrade-13.0` for 13.0, `odoo-<v>` from 14.0;
- the trees of the client's OCA repositories at that version.

The modules are then walked with `chain_fates`. Only the steps that still have gaps trigger the full
listing:
1. `system.github_org_repos("OCA")`, over `urllib` and paginated, gives the repository names;
2. the missing `<repo>-<version>` trees are cloned into `.repos/oca-trees/`, each a single command
   (`git clone --depth 1 --filter=blob:none --no-checkout -b <version>`), previewed and confirmed as one
   plan. A clone that fails because the branch does not exist writes an `.absent` marker, so it is not
   tried again;
3. the names are rebuilt from every tree, and gaps are recomputed.

On the first client, the client's own repositories covered most steps. The full listing is a one-time
cost per host and version: about 270 repositories.

The walk is a pure function:

```python
availability(installed, fates, found_at_step) -> rows
```

`found_at_step` is `{version: {module: repo}}`. Each row holds the module, its origin, the name at each
step, the repository at each step or `MISSING`, and a `moved` flag.

### 5. The scanner has a declared positive control

The patterns are a tuple of `(name, regex, control line)`. Before any scan, each regex must match its own
control line, and a failure refuses the step. The scan covers `*.py` files of custom installed modules
only, excluding `tests/` and `migrations/` directories: tests reach mocks, and migrations run once. It
records `(module, file, line number, pattern name, the stripped line up to 160 characters)`.

The patterns are:

| Group | Patterns |
|---|---|
| HTTP | `requests.`, `urllib`, `http.client`, `httplib` |
| Mail and file transfer | `smtplib`, `ftplib`, `paramiko`, `pysftp` |
| SOAP | `zeep`, `suds` |
| Sockets | `socket.` |
| Processes | `subprocess`, `os.system`, `os.popen` |
| RPC | `xmlrpc`, `jsonrpc` |
| Job queue | `with_delay(` |
| Odoo's IAP client | `iap_jsonrpc`, `iap_tools` |

## Risks / Trade-offs

- **GitHub's unauthenticated API allows 60 requests an hour.** → The OCA listing takes three pages. It is
  cached in `.repos/oca-trees/.repos.json` with its date, and re-listed only on request.
- **A full listing clones hundreds of trees.** → It happens only for the steps with gaps, as one previewed
  plan, and the trees are small (a few hundred KB each).
- **A pattern scan finds code, not behaviour.** → A hit is recorded as "reads as a network call" for a
  person to read. A miss, with a working scanner, is reported as "no pattern matched", never as "safe".
