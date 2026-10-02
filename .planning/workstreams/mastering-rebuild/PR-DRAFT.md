## Scope
Fresh local Company, Person and Relationship mastering qualification and proved unused code/test cleanup. **Draft: the original task remains incomplete.** The operator selected local qualification only; no hosted deployment or merge is included.

## Changes
- Remove three unreachable modules (bronze daily-index loader, reference seeding loader, standalone Security publisher) and five obsolete cases; exact caller proof and removed node IDs are in the inventory.
- Add a pinned two-Company/two-Person cohort, PostgreSQL acceptance for canonical relationship endpoints, replay, restricted-role denials and local publication read-back.
- Add a local qualification runner that retains logs/JUnit and rejects missing prerequisites, skipped PostgreSQL acceptance and timeouts.
- Consolidate AGENTS.md/CLAUDE.md and document current mastering operations.
- Include Claude's continuation handoff and prepared external memory corrections.

## Verification
- Rebased on GitHub main #779 (`542a9fa0`); all existing changes retained by range-diff.
- After rebase: 13 affected cases passed in 9.10s.
- Prior full non-database run, 2026-10-01: 1,132 cases passed in 107.90s.
- 25 shell scripts passed bash syntax checks.
- 1,424 cases collected: 395 unit, 490 MDM, 247 architecture, 292 integration.
- Five cases removed and five added: total case count unchanged. No measured CI speed improvement claimed.
- Local PostgreSQL qualification failed at the Docker prerequisite, with no skips; `qualified=false`. No existing database, Docker volume or external memory was changed.
- Documentation handoff checked against current branch/main, implementation and ticket; `git diff --check` passed.

## Remaining gates
- [ ] Real PostgreSQL 16 Company/Person/Relationship acceptance with restricted roles and physical publication read-back.
- [ ] Complete integration and local qualification gate.
- [ ] Exact local database inventory, recoverability and removal of confirmed unused targets.
- [ ] Apply authorized external memory corrections; Codex notes access is now available, corrections remain unapplied.

The EMPLOYED_BY fixture is synthetic and establishes no employment fact. A full Person acquisition/preparation reader remains separate work. Timeout termination can bypass fixture teardown; Claude should inspect exact run-owned leftovers.

## Claude handoff

[Source draft PR #780](https://github.com/paulananth/edgartools-platform/pull/780), created and verified 2026-10-02 08:52 ET. GitHub access is restored; Colima, Docker server 29.5.2 and the PostgreSQL 16 image are available. Qualification has not been rerun after access was restored.

[Continuation instructions](https://github.com/paulananth/edgartools-platform/blob/codex/mastering-rebuild-20261001/.planning/workstreams/mastering-rebuild/HANDOFF-to-claude-20261002.md)
[Task checklist and evidence](https://github.com/paulananth/edgartools-platform/blob/codex/mastering-rebuild-20261001/.planning/workstreams/mastering-rebuild/TICKET.md)
[Deletion inventory](https://github.com/paulananth/edgartools-platform/blob/codex/mastering-rebuild-20261001/.planning/workstreams/mastering-rebuild/INVENTORY.md)

Claude should continue from this PR head on a dedicated `claude/` branch/worktree and link a continuation PR, preserving the Codex branch and unrelated shared work.
