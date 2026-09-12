Type: grilling
Status: resolved
Blocked by: 01

## Question

**Reshaped by Ticket 01's finding:** the write-time bug appears to already
be gone — a side effect of the unrelated OOM-driven CRD-batching refactor
(`869003da`, 2026-08-21) — with zero recurrence across 140,907 historical
duplicate groups and 4,116 new rows written in the 3+ weeks since. The
exact mechanism inside the old, now-replaced code wasn't conclusively
pinned down. So the real decision here is narrower than originally
scoped:

1. **Is the circumstantial evidence (0 new duplicates in 3+ weeks of
   continued writes) sufficient to conclude the write-time bug is already
   fixed, with no new code needed** — making Ticket 03 a no-op or a small
   monitoring/confirmation task instead of an implementation task? Or does
   this need a positive reproduction (rebuild the old code path in a test
   harness and prove it fails, then prove the new code doesn't) before
   being trusted?
2. If a positive test IS wanted despite not knowing the exact old-code
   mechanism: is a live-shaped regression test even constructible without
   that mechanism, or would it necessarily just re-assert "the new code
   doesn't duplicate obvious cases" (weaker than a true regression test
   that fails on the old code and passes on the new)?
3. Assuming no code fix is needed: should Ticket 03 be closed/skipped
   outright, or repurposed as a lightweight live-monitoring addition
   (e.g., a periodic check/alert for new MANAGES_FUND duplicate groups)
   so a real regression would be caught quickly if this reasoning turns
   out wrong?

Use `/grilling` and `/domain-modeling` per this map's Notes.

## Answer

Grilled over one round, user-agreed on all three points.

1. **Circumstantial evidence accepted as sufficient — no code fix needed.**
   3+ weeks of clean production writes (4,116 new rows, 0 new duplicate
   groups) since the CRD-batching refactor (`869003da`) is strong enough
   evidence, especially since the refactor's own structural change
   (per-CRD-batch priming + per-batch commits, replacing one unconditional
   whole-type prime with no interim commits) is a plausible sufficient
   cause regardless of the exact old mechanism — a long-lived single
   transaction over the whole universe is exactly the shape that would
   let stale cache visibility go unnoticed, and per-batch commits close
   that window. Demanding a positive reproduction of now-dead code has a
   real cost not justified here.
2. **Ticket 03 repurposed, not closed**: from "implement + deploy a
   write-time fix" to a lightweight live-monitoring check (mirroring this
   repo's existing `mdm check-fence` precedent for "verify a fixed
   assumption stays true") that alerts if any *new* MANAGES_FUND
   relationship_id ever gets a duplicate active row again — cheap
   insurance against the unconfirmed-mechanism gap in Ticket 01's finding.
3. **Ticket 04's backlog-cleanup design is unaffected** — still a simple
   dedup pass (every sampled group was clean/conflict-free), and no
   longer needs to wait on Ticket 03's monitoring check (unblocked, see
   that ticket).
