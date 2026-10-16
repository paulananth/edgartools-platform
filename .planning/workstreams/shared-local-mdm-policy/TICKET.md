# Shared local MDM policy

The operator wants one permanent local MDM for Company lookups across agents.
Separate Git worktrees protect code edits; they do not require separate servers.

## Parts

- [x] Document the shared server default and isolated-test exception in AGENTS.md and CLAUDE.md — 2026-10-16 19:47 ET; both sections checked against the operator's shared-lookup decision.
- [x] Verify both instructions agree, preserve lifecycle ownership, and pass the overlap guard and whitespace check — 2026-10-16 19:47 ET; exact section comparison and required-clause checks passed, overlap guard clear for all three paths, git diff --check clean. Documentation only; no application behavior changed.
- [x] Learning → skill: none; this repository working rule belongs in AGENTS.md and CLAUDE.md — 2026-10-16 19:47 ET; both explicitly supersede the earlier per-agent-copy default while retaining optional test isolation.
