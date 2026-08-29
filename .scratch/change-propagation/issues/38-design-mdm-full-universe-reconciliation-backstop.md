# 38 — Design the periodic MDM full-universe reconciliation backstop

**What to build:** A decision (not an implementation) for the periodic
pass that catches match/survivorship drift a bounded, 1-hop incremental
pass structurally cannot see — multi-hop ripple effects, near-miss
matches that only become visible once enough of the universe has been
re-scanned.

**Blocked by:** None — the *need* for this backstop is already decided
(Ticket 06); its internal design is not.

**Status:** resolved

## Question

What should the periodic full-universe reconciliation backstop actually
check, how often should it run, and how does it relate to the bounded,
1-hop candidate-neighbor expansion Ticket 06 decided for the incremental
path (Change Propagation Run → MDM resolution → 1-hop relationship-edge
re-check)?

Decide: what "drift" this backstop specifically looks for that the
incremental path wouldn't catch (multi-hop ripple? near-miss matches
below the incremental path's confidence threshold? both?); its cadence
and cost profile (compare against the existing `Identity Backstop Sweep`
naming precedent and cadence, a different subsystem but a close analog
worth checking before inventing a new cadence policy from scratch); how
findings get surfaced (auto-corrected, or routed through the existing
`stewardship.py` review queue — `MdmMatchReview`/`accept_review`/
`reject_review` — so a human stays in the loop for anything not
mechanically certain); and how this relates to the release-readiness
map's already-built periodic full-parity mechanism (`Relationship
Generation Snapshot`, `Per-Type Exact Relationship Parity` — a
point-in-time release-gate audit, not an ongoing incremental-correctness
backstop, but close enough in shape that this ticket should explicitly
say why it isn't the same thing before building something that
duplicates it).

## Notes

Surfaced while resolving [06 — Decide MDM affected-key closure and
publication outbox](06-decide-mdm-closure-and-outbox.md) — confirmed
twice now (once by `mdm-ahead-of-silver`'s own Ticket 04, once here) that
this backstop is a real, needed, and genuinely undesigned piece.

## Answer

Grilled 2026-08-29. Term: **MDM Reconciliation Backstop** (`CONTEXT.md`).

**Drift in scope (three miss classes, one pass):**
1. Multi-hop ripple a 1-hop incremental pass cannot see (Ticket 06).
2. Below-threshold near-misses a sequential matcher never re-sees
   (`mdm-ahead-of-silver` Ticket 04).
3. Skip-if-unchanged hash staleness (live today: matching `source_content_hash`
   skips matching/survivorship, so a later better candidate is never re-scored).

1-hop itself is **not implemented**. Classes 2 and 3 are useful against
today's `mdm run`; class 1 becomes an *incremental* miss only once 1-hop
ships. The backstop does not wait on that.

**Not Per-Type Exact Relationship Parity / `mdm verify-graph`.** That gate
proves a frozen MDM edge set equals the hosted graph at a Release Data
Watermark. It does not re-run matching or walk neighbors. A graph mismatch
is a publication bug; this backstop is a resolution bug. Do not implement
it as another `verify-graph`.

**Not Identity Backstop Sweep.** That is the Sunday company-identity SEC
refresh (18h bound, Identity Refresh Slot). Different glossary term,
different schedule, different store. Do not share the slot or the name.

**Pass shape:** existing `MDMPipeline.run_all()` — all six entity types
then `derive_relationships()` — with skip-if-unchanged **off** and **no
`--limit`**. No new graph walker. `run_all()` already enqueues the
publication outbox on non-trivial output; the backstop inherits that.

**Finding disposition** (already-resolved golden records):
- Same `entity_id` → no-op.
- `AUTO_MERGE` onto a different entity → existing `merge_entities`.
- Review band (`>= review_min`, `< auto_merge_min`) → **insert**
  `MdmMatchReview` (first real producer); do not merge.
- Score below `review_min` against the current assignment → do not
  auto-split a live golden record; queue for review only if it now prefers
  someone else, otherwise no-op.
- Relationship writes stay the existing idempotent derive.

**Cadence:** monthly, MDM-owned EventBridge, **not** Sunday. Off by default
(same enable/disable flag pattern as publication-drain on `mdm-utility`).
No copied 18h SLO — first build measures duration, then sets the bound.
Weekly is the ceiling only after that measurement.

**Overlap:** exclusive lease with ordinary `mdm run` resolution
(`daily_incremental` / `load_history` Stage 2). If the other is in flight,
fail closed and retry on the next slot. Do not overlap two universe scans
and hope per-row idempotency is enough.

**Follow-up tickets (not blocked on each other):**
- [49 — Implement 1-hop MDM candidate-neighbor expansion](49-implement-one-hop-mdm-candidate-neighbor-expansion.md) — Ticket 06's incremental pass, still unbuilt.
- [50 — Build the MDM Reconciliation Backstop](50-build-mdm-reconciliation-backstop.md) — this design.
