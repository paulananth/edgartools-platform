# Decide GLEIF delta-gap recovery and completeness proof

Type: grilling
Status: resolved
Blocked by: 07, 08

## Question

How does a daily GLEIF consumer recover when its expected 24-hour delta is
missing, late, corrupt, or no longer overlaps the last applied publication?

## Recommendation

Checkpoint exact publication IDs and baselines per source family. Use a larger
official delta only when it demonstrably covers the last applied baseline;
otherwise capture a full Golden Copy and reconcile before advancing the MDM
watermark. A failed family never advances, and Level 1, relationship, and
exception checkpoints remain independently replayable.

## Done when

The accepted continuity checks, fallback order, fail-closed states, monthly
full-snapshot proof, and operator evidence are explicit.

## Answer

Checkpoint exact publication and baseline identities independently for Level 1,
relationship, and exception families. Accept a larger official delta only when
its metadata and complete captured inventory prove overlap from the last applied
baseline. Otherwise capture and reconcile a complete Golden Copy before
advancing that family's MDM watermark. Missing, late, corrupt, discontinuous, or
partially applied input is fail-closed; one family cannot advance another.

The monthly proof binds complete source inventory and hashes to normalized
record counts, added/changed/retired dispositions, MDM projections, deferred and
review queues, downstream parity, and an independently replayable run. Operator
evidence names the failed continuity check and selected recovery path.

Accepted by the user during the 2026-09-12 `/grill-with-docs` session.
