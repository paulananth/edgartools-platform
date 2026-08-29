# 49 — Implement 1-hop MDM candidate-neighbor expansion

**What to build:** When a source row changes, also re-check entities with
a *direct* existing relationship edge to the resolved entity (known
officers, adviser, auditor) — not the whole graph and not zero expansion.
Ticket 06 decided this as the incremental Affected-Key Closure for MDM;
nothing implements it. `MDMPipeline.run_all()` still sweeps entity-type
loops plus `derive_relationships()` with no neighbor expansion.

**Blocked by:** 06 — Decide MDM affected-key closure and publication
outbox (resolved)

**Status:** ready-for-agent

Type: task

- [ ] A changed source row's resolved entity expands to its 1-hop
  relationship neighbors (direct `mdm_relationship_instance` edges only)
  and those neighbors are re-checked in the same `mdm run`, not deferred
  to the MDM Reconciliation Backstop.
- [ ] Unrelated entities are not re-resolved. Cost stays proportional to
  the change plus direct neighbors, not the universe.
- [ ] Skip-if-unchanged still applies to neighbors whose source hash is
  unchanged — 1-hop re-checks the *relationship/survivorship* implication,
  it does not become a skip-off universe scan (that is Ticket 50).
- [ ] A test proves a changed company re-checks a directly-linked person
  (or adviser/auditor) and does not re-check a 2-hop entity.

## Notes

Surfaced while resolving [38 — Design the periodic MDM full-universe
reconciliation backstop](38-design-mdm-full-universe-reconciliation-backstop.md).
Ticket 06 already decided 1-hop; this ticket is the missing implementation.
The MDM Reconciliation Backstop (Ticket 50) covers multi-hop, near-miss,
and hash-skip and must **not** wait on this ticket.
