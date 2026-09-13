# Select the first GLEIF MDM delivery slice

Type: grilling
Status: resolved
Blocked by: 03, 04, 10, 11, 12, 13, 14, 15

## Question

What is the smallest Company Legal-Entity Enrichment slice that proves durable
source capture, safe identity binding, useful attribute lift, typed
relationships/exceptions, replay, and downstream MDM publication?

## Recommendation

Start with shared Level 1/relationship/exception capture, manually approved or
deterministic Company-to-LEI source links, legal form/jurisdiction/lifecycle and
registration evidence, direct/ultimate accounting-parent evidence, and
reporting exceptions. Keep Fund, Branch, Security mapping, and unsupported
parent endpoints captured but unpublished until their domain consumers exist.

## Done when

The included fields/relationships, excluded consumers, cohort/backfill scope,
success metrics, and release/no-go gates are accepted.

## Answer

Proceed with a bounded Company tracer bullet. Capture a verified complete
current Level 1, relationship, and exception baseline, then daily 24-hour
deltas. Revalidate the 308 adjudicated seed links and publish only approved or
deterministic unique Company-to-LEI links. Project the fields accepted in the
survivorship decision; capture all direct/ultimate consolidation records and
reporting exceptions; publish a typed edge only when both endpoints are
accepted Companies. Include bi-weekly OpenCorporates mapping as corroborating
source evidence, never merge authority.

Fund, Branch, Security, and unsupported endpoints remain captured and
nonpublishing under the parent program. The initial backfill is the current
complete source baseline plus revalidated seed links, not an unreviewed match of
the full MDM universe. Release requires complete/hash-verified inventory,
terminal candidate dispositions, zero name-only automatic links, zero duplicate
active bindings, complete provenance, deterministic replay, independent
fail-closed checkpoints, exact applicable downstream parity, rollback proof,
approved runtime/memory/storage/request cost, and Release Owner GO. Future
heuristic auto-linking needs an independent holdout with a lower confidence
bound of at least 99.9% and zero uniqueness violations.

Accepted by the user during the 2026-09-12 `/grill-with-docs` session.
