# Clean MDM Pre-Merge Staging Proposal

Label: `wayfinder:map`

## Destination

A single, evidenced proposal document — checked against Clean MDM's actual
`merge.py`/`merge-stage.md`, not assumed — recommending a **persisted,
reviewable staging state** for candidate merges, sitting between identity
matching and the atomic Merge Stage commit. Ready for Codex/Grok to accept,
adapt, or reject. This map does not implement anything and does not touch
Clean MDM's own files.

## Notes

- Repo: `edgartools-platform`, worktree
  `edgartools-platform-worktrees/claude-mongo-sparql-agent-contract`, branch
  `claude/mongo-sparql-agent-contract`.
- Origin: the operator asked (in the `agent-open-query-interface` line of
  work) whether Clean MDM's rebuild follows the match/diff/multi-source-merge/
  insert-or-update pattern found in legacy MDM's `resolvers/base.py`, and to
  add a "pre-merge stage after de-duplication" to Clean MDM's plan if it
  doesn't already have one.
- **Ownership boundary, deliberately kept**: `.scratch/clean-mdm/` and
  `docs/specs/clean-mdm/` are Codex/Grok-owned, active work (open PR #657,
  134 passing tests, an accepted Q1-Q16 policy interview from 2026-09-18).
  Per CLAUDE.md's "Treat current Codex or Grok work as protected unless the
  user explicitly hands it off" and Clean MDM's own map's "do not reopen
  accepted policy choices," the operator chose (2026-09-19, this session) to
  keep this a proposal on a separate map rather than a direct edit to their
  files. Read-only reference only.
- Checked live against `origin/codex/clean-mdm-integration` (base
  `e14eb74b` per `docs/specs/clean-mdm/state-of-build.md`).
- What Clean MDM already has, confirmed by reading `merge.py`/`merge-stage.md`
  directly (not inferred): the **Merge Stage is already more rigorous** than
  legacy's pattern (steward-owned field authority order, hard-veto identifier
  conflicts, evidence-bound reversal) — but automated duplicate detection is
  **deliberately disabled** right now (`merge.py:5`: "Neither auto binding
  nor automatic consolidation is enabled in this release"; gated behind Q11's
  99.9%-precision calibration bar). Matching, conflict detection, and field
  selection all happen inside **one atomic transaction**
  (`MergeStage.apply()`, `merge.py:108`) — `merge-stage.md:24-29` is explicit
  that no path writes master state around that single entry point. There is
  already a `preview: bool` dry-run flag, but no *persisted* staging state
  that survives past one `apply()` call.
- Operator's answer to "what should the new stage give that the existing
  preview/conflict-check doesn't" (grilling round, this session): **a
  persisted, reviewable staging state** — matched/deduped candidates written
  to a durable staging table before commit, so a steward can review
  asynchronously, across sessions/transactions, the way legacy's
  `mdm_entity_attribute_stage` lets an operator inspect staged candidate
  field values before survivorship picks a winner ([legacy DDL
  inventory](../agent-open-query-interface/research/05-mdm-postgres-ddl-inventory.md),
  [legacy call sequence](../agent-open-query-interface/research/06-mdm-postgres-call-sequence.md)).
- Skills: `/wayfinder`. No `/grilling`/`/domain-modeling` decision tree
  needed beyond the one round already run — the destination is a single
  proposal document, not a multi-step decision chain, and every open design
  question the proposal itself surfaces belongs to Clean MDM's owners, not
  to this map.

## Decisions so far

- [Write and evidence the pre-merge staging proposal](issues/01-write-premerge-staging-proposal.md)
  — full proposal in the ticket's Answer: a `mdm_v2.merge_candidate`-shaped
  staging table, written after identity/conflict resolution but before
  `MergeStage.apply()`'s commit, holding candidate group membership,
  detected conflicts, proposed field selections, and a review status. Flags
  the one hard constraint (must not become a second master-state write path)
  and four open design questions for Clean MDM to resolve, not this map.

## Not yet specified

- None. The proposal is the deliverable; whether Codex/Grok accept, adapt,
  or reject it — and how, if accepted — is entirely theirs to decide and
  isn't tracked here.

## Out of scope

- Any actual implementation of the staging table or a change to
  `MergeStage.apply()`'s transaction boundary — that's Clean MDM's decision
  surface, not this map's, per the ownership boundary above.
- Any edit to `.scratch/clean-mdm/` or `docs/specs/clean-mdm/` — reference
  only.
