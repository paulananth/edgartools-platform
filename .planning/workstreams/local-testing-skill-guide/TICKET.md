# Connect local testing policy to the implemented lifecycle

Status: local testing guide verified; runtime PR #1028 merged; final documentation CI required before landing.

- [x] Inspect current main, worktree ownership and generic skill requirements (guard clear; 2026-10-16 19:14 ET).
- [x] Replace pending implementation text with the real script, empty-store distinction and backup/copy behavior; state the checkout requirement in LOCAL-TESTING.md (compared with runtime guide and CLI; 2026-10-16 19:14 ET).
- [x] Verify affected skill checks and review documentation (68 genericity checks passed in 0.31 seconds after rebasing onto Claude PR #1026; Standards and Spec agree with the runtime guide, GoF not applicable to this documentation-only diff; 2026-10-16 19:31 ET).
- [x] Publish and obtain green CI; runtime prerequisite merged (PR #1029 all six checks passed at 69cc5aa2; runtime #1028 merged at d71b64a3; final documentation-only head still requires its CI gate before landing; 2026-10-16 19:23 ET).
- [x] Clarify the main skill page checkout introduction after Claude PR #1026 merged; rebased onto its changes and retained them (overlap guard passed before commit; 2026-10-16 19:30 ET).
- [x] Close the runtime ticket checklist using its merged CI evidence (six green checks and merge d71b64a3 verified; 2026-10-16 19:23 ET).
- [x] Learning → skill: data-platform/LOCAL-TESTING.md must distinguish empty infrastructure from qualified source data and name implemented commands (documentation and genericity checks verified; 2026-10-16 19:15 ET).
