# 50 — Build the MDM Reconciliation Backstop

**What to build:** The periodic full-universe MDM match, survivorship, and
relationship re-derivation pass Ticket 38 designed. Existing
`MDMPipeline.run_all()` with skip-if-unchanged **off** and **no `--limit`**,
plus a real `MdmMatchReview` producer, an exclusive lease against ordinary
`mdm run`, and an off-by-default monthly EventBridge rule on `mdm-utility`.

**Blocked by:** 38 — Design the periodic MDM full-universe reconciliation
backstop (resolved)

**Status:** ready-for-agent

Type: task

- [ ] A dedicated CLI / `mdm-utility` mode runs `run_all()` across all six
  entity types then `derive_relationships()`, with skip-if-unchanged
  disabled and no default `--limit`.
- [ ] Review-band hits insert `MdmMatchReview` (first producer).
  `AUTO_MERGE` onto a different entity uses existing `merge_entities`.
  Same `entity_id` is a no-op. A live golden record is never auto-split
  because a backstop score went cold.
- [ ] Exclusive lease: this pass and ordinary `mdm run` resolution cannot
  overlap; in-flight conflict fails closed and retries on the next slot.
- [ ] Off-by-default monthly EventBridge rule, MDM-owned, not Sunday,
  same enable/disable deploy-flag pattern as publication-drain. First
  measured run sets the duration bound; do not copy Identity Backstop
  Sweep's 18h SLO.
- [ ] A test proves skip-if-unchanged is off (an unchanged hash is still
  re-scored), a review-band pair writes `MdmMatchReview`, and a second
  overlapping `mdm run` is rejected.

## Notes

Design is the Answer on [38 — Design the periodic MDM full-universe
reconciliation backstop](38-design-mdm-full-universe-reconciliation-backstop.md).
Do not implement this as `mdm verify-graph` or as a step on the Identity
Refresh Slot. Do not block on [49 — Implement 1-hop MDM candidate-neighbor
expansion](49-implement-one-hop-mdm-candidate-neighbor-expansion.md).
