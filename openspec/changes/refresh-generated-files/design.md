## Decisions

- **One list of generated files.** `generated_files(cfg, interpreters)` returns `(path, content, mode)` for
  every file the tool writes. Creating a workspace and refreshing one both consume it, so they cannot
  disagree. `plan_workspace_links` holds the idempotent directories and OCA symlinks.
- **Diff, then back up.** `plan_refresh_files` takes an injected reader and stays pure. It writes only
  changed files and copies each existing one to `<file>.bak` first. Rejected alternatives:
  - *overwrite silently*: loses hand edits;
  - *refuse edited files*: blocks updates;
  - *timestamped backups*: they accumulate. One `.bak` per file is the latest previous version, and the
    preview names each one.
- **Read interpreters back from `pyvenv.cfg`.**
  - Workspace profiles do not record interpreters, and the venv is the truth.
  - `uv` writes a `uv = …` key and `version_info`; the stdlib `venv` writes `version`. Both formats were
    observed on this host.
  - A choice read back is kept as it is, even when outside the range, because it is what exists.
- **Exact file content.** The heredoc used to be `{content}\nEOF`, which added a blank line to content that
  already ends in a newline. The body now ends where the content does. Refresh treats a trailing-newline-only
  difference as current, so older workspaces do not get a round of pointless backups.
- **Translations enforced, not remembered.** A test walks the package AST and collects the literals passed to
  the translation chokepoints (`t`, `tf`, `choose`, the prompts, `level_text`, `Command`, table headers). It
  requires each one in the catalog.

## Risks / Trade-offs

- A second refresh overwrites the previous `.bak`. → Stated in the prompt and the docs.
- The translation test sees literals only. A string built at runtime and passed to `t` escapes it. → Those
  strings already use `tf` with a literal template, which the test does see.
