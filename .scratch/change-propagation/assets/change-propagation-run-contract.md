# Change Propagation Run contract — worked examples

Resolving [Ticket 04 — Prototype the Change Propagation Run contract](../issues/04-prototype-change-run-contract.md).
Linked as an asset per wayfinder convention rather than pasted into the ticket.

## What this is

Ticket 04 asked for prototyped example schemas for a "Change Propagation
Run" and its parts (run manifest, change envelope, expected-producer set,
stage manifest, outcome ledger, replay/repair linkage, publication
identity). By the time this ticket was actually grilled, Tickets 13-25 had
already shipped real, tested code covering almost every piece — CONTEXT.md
already carries precise definitions for **Change Propagation Run**,
**Source Change**, **Lifecycle Diff**, **Expected Producer Set**, **Repair
Revision**, and **Immutable Source Conflict** that predate this ticket's
resolution. So this document is not a new prototype artifact — it is a
worked-example trace showing how each of the ticket's five required
scenarios is already proven by shipped code, plus the concrete mapping from
Ticket 04's original vocabulary onto CONTEXT.md's existing terms, and an
honest accounting of what genuinely isn't built yet.

## Vocabulary mapping (Ticket 04's terms → CONTEXT.md's existing terms)

| Ticket 04 asked for | Maps onto | New schema needed? |
|---|---|---|
| Immutable run manifest | **Change Propagation Run** — a derived identity (`cause_reference`), not a new table. The Run is a view over existing rows grouped by that shared key. | No |
| Change envelope | **Source Change** (CONTEXT.md) — already carries the revision link, Run link (`cause_reference`), and Bronze evidence reference. | No |
| Expected-producer set | **Expected Producer Set** — already built (Ticket 19: `ExpectedProducerSpec`, `source_expected_producer`). | No (built) |
| UPSERT/RETIRE/SCOPE_COMPLETE operation | **Lifecycle Diff** outcome (changed/new upserts, scope-proved retirements, unchanged, no-impact) | No |
| Stage manifest / outcome ledger (MDM/gold/graph) | A generic shape *to be instantiated later* — generalize `source_processing_decision`/`source_expected_producer`'s shape, parameterized by stage name | Deferred to Tickets 06/07/08 |
| Replay/repair linkage | Existing idempotency (candidate_id dedup, quarantine-reference dedup) + **Repair Revision** (`RevisionRelationship.REPAIR`, Ticket 25) | No |
| Publication identity | `cause_reference`, as *one input component* of the eventual composite **Decision Watermark** (CONTEXT.md line 405 — already defined on the read side; Ticket 09 owns assembling the full tuple) | No, for this ticket |
| Affected-Key Closure | Trivially `{logical_source_key}` today — no stage yet expands beyond one key. Real expansion (MDM entity/relationship dependents, gold DAG dependents, graph partition dependents) is Tickets 06/07/08's job when built. | Deferred |

## The five required scenarios, traced to existing proof

### 1. Duplicate no-op delivery

**Proven.** `tests/acquisition/test_discovery.py::test_replaying_the_same_manifest_performs_no_duplicate_decision_or_network_work`
— replaying the same Discovery Manifest performs zero duplicate decisions
and zero network calls. Confirmed again at real-infrastructure scale by
Ticket 29's prod dry run: a full `drive-filing-discovery-for-date` run and
its no-op replay produced identical row counts, zero re-fetches, and zero
errors.

### 2. Corrected content under a repair attestation

**Proven.** `tests/acquisition/test_conflict.py::test_resolve_conflict_accepting_conflicting_materializes_a_repair_revision`
— an operator accepting the conflicting evidence over the original
materializes an immutable `REPAIR` child revision naming both the accepted
and rejected evidence, the operator's authorization, and the reason,
without mutating the original. `tests/integration/test_conflict_postgres.py::test_resolve_conflict_concurrent_opposing_outcomes_never_orphan_a_revision`
additionally proves this holds under a genuine concurrent-resolution race.

### 3. Replacement-scope disappearance

**Partially proven — honest gap, not overclaimed.** At the *family-writer*
level, `tests/acquisition/test_reference_catalog_silver_acceptance.py::test_a_fresh_snapshot_replaces_the_prior_scope_for_the_local_candidate`
replaces a two-ticker scope with a one-ticker scope and confirms the
dropped ticker is gone from the local candidate database — this direction
of the scenario is genuinely proven.

**What is not proven**: `silver_protection.py`'s `merge_candidate_into_canonical`
documents, in its own words, that it "never deletes a row that exists only
in canonical" — so once a candidate merges into canonical, that same
retirement does **not** propagate. This is not a new discovery: Ticket 02's
original table-change-semantics inventory already recorded this gap for
the Snowflake-landing-export layer; Ticket 23 confirmed the same gap
independently applies at the DuckDB candidate-to-canonical merge layer.
Fixing the conservative "never shrinks a scope" policy is a real, separate
design change (it exists specifically to protect a windowed CIK-slice
candidate from looking like the whole table shrank) — out of this ticket's
scope, and out of Ticket 23's scope. Whoever eventually builds real
scope-shrink propagation should start from these two tickets' findings, not
rediscover the gap.

### 4. A partial producer retry

**Proven, with a scoping note.** `tests/acquisition/test_processing.py::test_record_producer_outcome_requires_every_producer_before_published`
proves the actual property this scenario cares about: with two expected
producers, settling the first leaves the Processing Decision `PENDING`
(not prematurely published), and only settling the second converges it to
`PUBLISHED` — partial producer progress never causes early or double
publication.

**Scoping note**: this proves partial-then-complete *convergence*, not
literal retry of a producer that already recorded `FAILED` on the same
Processing Decision — `test_record_producer_outcome_conflicting_replay_raises`
shows a settled outcome cannot be silently overwritten, and Ticket 19's
own ordering rule makes a `FAILED` prior permanent for that key, not
transient. A genuine "retry after failure" only happens through a *new*
revision after operator repair (Ticket 25), not by re-recording the same
producer's outcome — this is a deliberate design choice already documented
above (Repair Revision), not a gap.

### 5. An out-of-order older event

**Proven.** `tests/acquisition/test_processing.py::test_seal_blocks_while_prior_revision_pending`
and `test_seal_blocks_forever_after_prior_revision_failed_until_repaired`
show that sealing a *later* position's Processing Decision is blocked
until the *immediately preceding* position for the same key has settled
(`PUBLISHED`) — so a later-arriving event can never be processed ahead of
an earlier, still-unsettled one, regardless of network arrival order.
`tests/acquisition/test_revisions.py::test_observation_positions_preserve_gaps_left_by_failed_decisions`
shows positions are reserved at decision time (not renumbered at
materialization), so a slow-arriving older event still lands at its
correctly-reserved earlier position once it does arrive.

## Field coverage against the ticket's required list

Every "change" (a Source Change bound to one Logical Source Revision)
already carries: source identity/version/hash (three versioned hashes:
raw evidence, canonical-source, domain-content), business key
(`source_family` + `logical_source_key`), operation (its Lifecycle Diff
outcome), domain-content hash, causal run (`cause_reference`), and
Affected-Key Closure (today, trivially the singleton key). None of these
embed secrets or mutable infrastructure identifiers — proven structurally
and behaviorally by `test_revision_schema_and_api_reject_run_id_arrival_time_object_path_pointer_and_etag_as_identity`
(Ticket 18) and `test_replaying_materialize_from_capture_at_different_wall_clock_times_yields_the_same_revision`.
