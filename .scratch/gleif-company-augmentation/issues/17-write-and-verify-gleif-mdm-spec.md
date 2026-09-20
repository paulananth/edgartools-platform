# Write and verify the GLEIF MDM enrichment specification

Type: task
Status: open
Blocked by: operator decision — the [Shared Foundation spec](../../../docs/specs/mdm-enrichment/shared-foundation.md) was written 2026-09-19 but is not yet "fixed" in this ticket's sense: it carries marked *Open* items (costs, observability thresholds, storage-class schedule, IAM) and two Clean MDM proposals still awaiting review (pre-merge candidate table, per-family checkpoint key). Whether this consumer spec may be written against that state, or must wait for those to close, is the operator's call — not decided here.

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
