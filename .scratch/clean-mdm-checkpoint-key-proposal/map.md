# Clean MDM Per-Family Checkpoint Key Proposal

Label: `wayfinder:map`

## Destination

A single, evidenced proposal document — checked against Clean MDM's actual
`023_clean_mdm.sql`, `merge.py`, `company_source.py`, and `recovery.md`,
not assumed — recommending that `mdm_v2.checkpoint` be keyed by
**(consumer, source_family, publication_family)** and carry the consumed
publication identity and continuity proof, instead of one scalar position
per consumer. Ready for Codex/Grok to accept, adapt, or reject. This map
does not implement anything and does not touch Clean MDM's own files.

## Notes

- Repo: `edgartools-platform`, worktree
  `edgartools-platform-worktrees/claude-mdm-enrichment-shared-foundation`,
  branch `claude/mdm-enrichment-shared-foundation`.
- Origin: [MDM Enrichment Shared Foundation](../mdm-enrichment-shared-foundation/map.md)
  ticket 05, Q1 (2026-09-19). The foundation locked ~8 independently
  checkpointed GLEIF publication families (its ticket 02) and "never advance
  a sibling family's checkpoint" (its ticket 03). Clean MDM's installed
  checkpoint table cannot express either. The operator chose to hand the
  required key to Codex as a proposal rather than decide `mdm_v2` DDL from
  the foundation map — same ownership reasoning as the
  [pre-merge staging proposal](../clean-mdm-premerge-staging-proposal/map.md).
- **Ownership boundary, deliberately kept**: `.scratch/clean-mdm/`,
  `docs/specs/clean-mdm/`, and `edgar_warehouse/mdm/clean/` are Codex/Grok-
  owned, active work. Read-only reference only; nothing there was edited.
- Checked live against `origin/codex/clean-mdm-integration` on 2026-09-19.
- Skills: `/wayfinder`. No grilling round needed — the decision to propose
  was made on the foundation map; this map only holds the deliverable.

## Decisions so far

- [Write and evidence the per-family checkpoint-key proposal](issues/01-write-checkpoint-key-proposal.md)
  — full proposal in the ticket's Answer: what exists, what the foundation
  needs, evidence that Clean MDM's own spec already describes the wider
  shape and that its first adapter already works around the narrow key,
  the proposed DDL shape, and the open questions left to Clean MDM.

## Not yet specified

- None. The proposal is the deliverable; whether Codex/Grok accept, adapt,
  or reject it is theirs.

## Out of scope

- Any change to `mdm_v2.checkpoint`, `commit_batch_core`, or any Clean MDM
  file — their decision surface.
- Reopening the accepted Q1–Q16 merge policy.
