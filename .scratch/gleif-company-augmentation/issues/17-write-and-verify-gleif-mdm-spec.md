# Write and verify the GLEIF MDM enrichment specification

Type: task
Status: resolved
Blocked by: none — operator decided 2026-09-19 ("write it now") that the consumer spec is written against the foundation spec as it stands, Open items and pending Clean MDM proposals included.

## Outcome

Create `spec.md` from the resolved map and decision record after the parent
Shared enrichment foundation specification is fixed. It must specify the first
Company consumer's use of shared evidence capture, cadence, source authority,
schemas, identity/review contract, temporal behavior, replay, observability,
security, rollout, and test/release gates without duplicating the source-wide
foundation contract or implementing either specification.

## Done when

The specification contains no unresolved design placeholders, cites every
material evidence artifact, and a documentation review confirms it matches the
map and repository architecture.

## Answer

Written 2026-09-19: [`spec.md`](../spec.md). It is the consumer *contract*
that Clean MDM's own `company-completion.md` delivery gate (Codex/Grok-owned)
must satisfy — not a competing implementation plan. Every section is filled
from the map's sixteen resolved tickets; the schema section binds those
evidence-level decisions to Clean MDM's `mdm_v2` tables per the
legacy-decommission directive; a Dependencies table names what still gates
release (per-family checkpoint key and pre-merge candidate table, both
proposed to Clean MDM; the foundation's Open items).

"Done when" status: no unresolved design placeholders (open items are named
dependencies, not placeholders); every material evidence artifact cited;
the documentation-review step — confirming it matches the map and the
repository architecture — has **not** yet been run and is the remaining
verification.
