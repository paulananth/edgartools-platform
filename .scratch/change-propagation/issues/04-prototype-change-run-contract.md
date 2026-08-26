# Prototype the Change Propagation Run contract

Type: prototype
Status: resolved
Blocked by: 01, 02, 03

## Question

What concrete, reviewable contract should represent a Change Propagation Run
and its stage-local work?

Prototype versioned example schemas for the immutable run manifest, change
envelope, expected-producer set, stage manifest, outcome ledger, replay/repair
linkage, and publication identity. Each change must be able to carry its source
identity/version/hash, business key, `UPSERT`/`RETIRE`/`SCOPE_COMPLETE`
operation, domain-content hash, causal run, and Affected-Key Closure without
embedding secrets or mutable infrastructure identifiers.

Exercise the prototype with at least: duplicate no-op delivery, corrected
content under a repair attestation, replacement-scope disappearance, a partial
producer retry, and an out-of-order older event. Link the resulting artifact
from the resolution rather than pasting it into this ticket.

## Answer

Grilled 2026-08-25, after re-checking against 13 tickets' worth of shipped
code that landed since this ticket was originally charted. CONTEXT.md
already carries precise, pre-existing definitions for almost everything
this ticket asked to prototype — **Change Propagation Run**, **Source
Change**, **Lifecycle Diff**, **Expected Producer Set**, **Repair
Revision**, and **Immutable Source Conflict** all predate this
resolution. This ticket's real job turned out to be narrower than
originally charted: map Ticket 04's vocabulary onto those existing terms,
identify what's genuinely still missing, and produce a worked-example
trace rather than new prototype code. Full mapping, scenario-by-scenario
proof, and one honest coverage gap are in the linked asset — not repeated
here.

**No new schema for the Run itself.** A Change Propagation Run is a
derived identity, not a new table: `cause_reference` (a required field on
every `SourceFetchDecisionRecord`, already populated uniformly by every
migrated source family's own discovery module as a deterministic digest)
is the Run's identity. The Run is a query over existing immutable ledger
rows grouped by that key, consistent with Ticket 03's "PostgreSQL is the
sole local authority... via existing ledger tables" decision — not a
fresh, redundant entity to keep synchronized.

**Change envelope = Source Change**, unchanged. **UPSERT/RETIRE/
SCOPE_COMPLETE = Lifecycle Diff's** existing outcome taxonomy, unchanged.
**Expected-producer set** is already fully built (Ticket 19). **Replay/
repair linkage** needs no new schema — existing idempotency (candidate_id
dedup, quarantine-reference dedup) plus Ticket 25's `RevisionRelationship.
REPAIR` already make both duplicate replay and corrected-content replay
converge correctly.

**Deferred, deliberately:** the generic "stage manifest"/outcome-ledger
shape for MDM/gold/graph (none of those stages exist yet) is recorded as
guidance — generalize `source_processing_decision`/`source_expected_producer`'s
already-proven shape, parameterized by stage name — but not drafted as
schema now, since building it without a second concrete consumer risks
guessing wrong (the same Speculative Generality this map's own Notes
warn against). Tickets 06/07/08 own drafting it when they actually need
it. Affected-Key Closure is, today, trivially the singleton
`{logical_source_key}` — nothing downstream expands beyond one key yet;
real expansion (MDM entity/relationship dependents, gold DAG dependents,
graph partition dependents) is those same tickets' job.

**Publication identity** is `cause_reference`, treated as *one input
component* of the eventual composite Decision Watermark — which turns out
to already be a defined concept (CONTEXT.md line 405), just documented
from the read side (the Agent Decision Surface's bundle-validity contract)
rather than the write-side propagation machinery that has to produce it.
Ticket 09 owns assembling the full tuple across all four stages; this
ticket only needed to guarantee its one component is stable and available
before any stage starts.

**One honest, non-overclaimed gap**, surfaced while tracing the five
required scenarios: "replacement-scope disappearance" is proven at the
family-writer level (a fresh snapshot correctly drops a member no longer
present) but **not** at the canonical-merge layer —
`merge_candidate_into_canonical` documents that it "never deletes a row
that exists only in canonical." Not a new discovery (Ticket 02's original
inventory already flagged it for Snowflake export; Ticket 23 confirmed it
also applies to the DuckDB merge layer) and not fixed here — fixing the
conservative "never shrinks a scope" policy is a real, separate design
change, out of this ticket's scope.

Worked-example trace with exact test citations for all five required
scenarios: [`assets/change-propagation-run-contract.md`](../assets/change-propagation-run-contract.md).
