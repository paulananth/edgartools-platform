# Add per-publication-family consumer checkpoints

Type: task
Status: resolved
Owner: Codex
Blocked by: none

## Accepted adaptation

[Claude's checkpoint proposal](../../clean-mdm-checkpoint-key-proposal/issues/01-write-checkpoint-key-proposal.md)
is consistent with accepted independent-family progress. Adapt it in the owned
Clean MDM schema, preserving immutable history and historical batch replay.
[Pickup reconciliation](../../handover/2026-09-20-codex-company-enrichment-reconciliation.md).

- Widen the existing primary key to consumer/source family/publication family.
- Existing rows retain empty family columns and null publication/proof. Do not
  infer coverage, merge rows, or rewrite old batch effects from consumer strings.
- Scoped commands require both family names, consumed publication identity and
  nonempty continuity-proof object; retain those in the cursor and batch effects.
- Preserve atomic expected/advancing fences, duplicate replay and rollback.
- Assessments fence the same family tuple. Sibling progress does not stale them.
- Source completeness and continuity verification remain a required separate
  adapter precondition. A stored proof is not a verified publication or a
  whole-publication completion flag, especially for a bounded partial batch.

## Verification

Use real PostgreSQL 16 and the restricted application role. Prove two families
for the same consumer advance independently, stale writes roll back, an assessed
proposal survives sibling progress, and old unscoped commands still replay.
Prove incomplete scope metadata fails without writing any master state.

## Design review

The checkpoint read and write live in the installed 023 capability (renamed by
027). No GoF refactor is warranted. Migration 029 replaces only exact guarded
checkpoint SQL fragments and the assessment snapshot predicate, retaining all
other commit checks and installed-file checksums. This avoids a second cursor
writer or duplicating the full commit capability.

## Verified 2026-09-20

47 tests passed, zero skips: all 44 Clean MDM PostgreSQL integration tests plus
3 native Company adapter tests. This includes upgrading a 028 database with a
committed batch and pending assessment, the existing manifest execution path,
registered-family enforcement and missing publication receipts.
[Evidence](../company-family-checkpoint-acceptance.json) pins source/report hashes.
Ruff and `git diff --check` pass. No persistent local or hosted migration occurred.
