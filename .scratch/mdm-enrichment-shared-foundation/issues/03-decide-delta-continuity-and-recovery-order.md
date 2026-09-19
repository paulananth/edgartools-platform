# Decide delta continuity proof fields and the recovery-order algorithm

Type: grilling
Status: open
Blocked by: none

## Question

The GoF review's Appendix C item 5 asks for delta continuity proof fields
and a deterministic recovery-order algorithm, at the foundation level (every
source family, not just GLEIF).

[GLEIF MDM enrichment evidence ticket 14](../gleif-company-augmentation/issues/14-decide-delta-gap-recovery.md)
already decided this for GLEIF specifically: "checkpoint each family
independently and reconcile a complete Golden Copy whenever official delta
continuity cannot be proven."

Does the foundation generalize this exactly — every publication family
proves continuity via its own published sequence/hash chain, and recovery
order is: **(1)** attempt the smallest delta span that closes the gap and
still proves continuity, **(2)** if no covering delta proves continuity,
fall back to a full Golden-Copy-equivalent reconciliation for that family
only (never advancing a sibling family's checkpoint) — or does a foundation
spanning multiple non-GLEIF sources need different continuity-proof fields
than GLEIF's own?

## Comments
