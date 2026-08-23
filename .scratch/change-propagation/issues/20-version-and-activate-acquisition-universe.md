# 20 — Version and activate the Acquisition Universe

**What to build:** Let operators change covered source families, CIKs, forms,
logical keys, and history boundaries through an explicit versioned transition
that proves baseline and catch-up coverage before activation.

**Blocked by:** 16 — Drive filing capture from SEC change discovery; 19 —
Complete the filing-to-Silver acceptance seam

**Status:** ready-for-agent

- [ ] The Source Family Registry versions logical keys, acquisition mode,
  completeness policy, discovery or polling policy, and required Silver
  producers as executable policy data.
- [ ] Adding coverage creates a scoped baseline and catch-up obligation;
  removing coverage ends future acquisition at an explicit boundary without
  retiring existing SEC facts.
- [ ] Registry or universe changes cannot activate until every affected family
  is complete through the declared boundary.
- [ ] A failed or incomplete transition leaves the previously active universe
  authoritative and exposes a precise blocker and next action.
- [ ] Callers select policies only through the registry; they cannot choose a
  Strategy implementation directly.
