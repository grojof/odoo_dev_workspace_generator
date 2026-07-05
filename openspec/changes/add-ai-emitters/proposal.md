> **PARKED** — this is an intentionally incomplete proposal (F4), captured so a future session can fill it
> forward (`/opsx:` → specs, design, tasks) and implement. It is not ready to apply as-is.

## Why

The tool is deliberately AI-agnostic: it installs no assistant, no MCP, and its substitute is a robust
generated README (that decision is what kept it simple, unlike the prior generation). Some users, however,
want an opt-in convenience that *emits* configuration for their own assistant (e.g. a per-workspace
`CLAUDE.md`, project skills, or agent definitions tuned for Odoo development and migration) — as text they
choose to enable, never installed or wired automatically. This change adds that as a strictly optional,
text-only emitter section.

## What Changes

- Add an **opt-in emitter** flow (its own menu entry / `emit` subcommand) that writes assistant configuration
  files into a target workspace or the project — and installs/downloads **nothing** (no runtimes, no `npx`, no
  binaries, no MCP servers). This is the hard boundary that the previous generation crossed and this one must
  not.
- Emit, per user selection: a per-workspace `CLAUDE.md` (Odoo dev/migration context, versions, paths,
  commands), optional skill/agent markdown stubs, and optionally an `.mcp.json` template the user can fill in
  themselves (emitted as inert text, never activated).
- Keep everything English, pure-templated, and behind explicit confirmation; the default remains "no AI
  files".

## Capabilities

### New Capabilities
- `ai-emitters`: opt-in, text-only generation of assistant configuration (CLAUDE.md / skills / agents /
  inert MCP templates) for a workspace or the project, installing nothing.

### Modified Capabilities
<!-- None expected; additive and independent of workspace/provision/migration. -->

## Impact

- **Code**: templates for the emitted files; a `workflows/emit.py` (or extend an existing surface) gated behind
  explicit opt-in; no new runtime dependency; no process that installs or downloads anything.
- **Docs**: an `docs/ai-emitters.md` explaining the opt-in nature and the no-install boundary.
- **Non-goals**: installing/running any assistant, MCP server, or Node tooling; making AI a default; coupling
  the generator to one specific assistant.

## To do next session

Fill forward: `specs/ai-emitters/spec.md` (requirements + scenarios: opt-in only, installs nothing, emits
valid text, default-off), `design.md` (which files, tokens, where they land), `tasks.md`. Then `/opsx:apply`.
