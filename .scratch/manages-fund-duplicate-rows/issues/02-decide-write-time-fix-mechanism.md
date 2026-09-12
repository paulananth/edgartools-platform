Type: grilling
Status: open
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

_(pending)_
