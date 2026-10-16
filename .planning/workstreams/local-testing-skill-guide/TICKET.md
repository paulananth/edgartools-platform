# Connect local testing policy to the implemented lifecycle

Status: documentation in progress; land after runtime PR #1028.

- [x] Inspect current main, worktree ownership and generic skill requirements (guard clear; 2026-10-16 19:14 ET).
- [x] Replace pending implementation text with the real script, empty-store distinction and backup/copy behavior; state the checkout requirement in LOCAL-TESTING.md (compared with runtime guide and CLI; 2026-10-16 19:14 ET).
- [x] Verify affected skill checks and review documentation (68 genericity checks passed in 0.29 seconds; Standards and Spec agree with the runtime guide, GoF not applicable to this documentation-only diff; 2026-10-16 19:15 ET).
- [ ] Publish and obtain green CI; merge after runtime PR #1028.
- [ ] ~~Clarify the main skill page checkout introduction~~ deferred until Claude PR #1026 and its active worktree release SKILL.md; overlap guard caught the shared path before any commit, and this branch leaves it unchanged.
- [x] Learning → skill: data-platform/LOCAL-TESTING.md must distinguish empty infrastructure from qualified source data and name implemented commands (documentation and genericity checks verified; 2026-10-16 19:15 ET).
