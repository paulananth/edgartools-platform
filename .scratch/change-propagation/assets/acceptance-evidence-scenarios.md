# Acceptance evidence scenarios — worked trace

Resolving [Ticket 11 — Prototype end-to-end incremental acceptance evidence](../issues/11-prototype-end-to-end-acceptance.md).
Linked as an asset per wayfinder convention. Mirrors Ticket 04's asset shape:
this is a worked-example trace against real shipped evidence, not a
speculative new subsystem.

## The schema

`edgar_warehouse/acquisition/acceptance_evidence.py`: one `AcceptanceEvidence`
record per scenario per Change Propagation Run (`cause_reference`).
Versioned (`schema_version`), secret-safe by construction (references,
hashes, enums, counts, durations only — the field set is locked by
`test_schema_fields_are_exactly_the_known_safe_set`), and fail-closed:
`build_acceptance_evidence` downgrades a caller's `passed=True` claim
whenever the record touches zero keys or carries any reason — the ticket's
own requirement that "success cannot be inferred from row counts or clean
logs alone."

`available=False` (via `unavailable()`) is a distinct, honest state from
`available=True, passed=False`: the former means this map has designed the
scenario but has no live evidence source for it yet; the latter means real
evidence was checked and failed.

## The 14 required scenarios, traced

| # | Scenario | Real evidence source | Adapter | Status |
|---|---|---|---|---|
| 1 | No-op replay | `ContentImpact.NO_IMPACT` (Ticket 03/18); prod-proven by Ticket 29's dry run (identical row counts, zero re-fetches on replay) | `from_content_impact` | **Bound** |
| 2 | Modified-key propagation | `ContentImpact.CHANGED`; `ParityVerdict` (Ticket 51/53, gated equal-or-superset of legacy) | `from_content_impact`, `from_parity_verdict` | **Bound** |
| 3 | RETIRE | Family-specific, not a shared type: `SilverDatabase._finalize_retirement` (Ticket 33, returns a retired-row count) and `_record_landing_retirements` (Ticket 23/35) each retire independently. No shared `RETIRE` evidence dataclass exists across families today — only a per-call integer count. | none yet | **Schema slot only** — a future adapter needs a shared retirement-count shape across families before this can bind; noted as real fog, not invented here |
| 4 | SCOPE_COMPLETE | `ExpectedProducerStatus` outcome `VERIFIED`/`NO_IMPACT` (Ticket 19); Ticket 22's count+digest `scope_reference` recording | `from_expected_producer_status` | **Bound** |
| 5 | Concurrent producers | `PriorRevisionNotSettled` (Ticket 19 bullet 4) — blocks a later revision for the same key until the prior one settles; proven under genuine Postgres concurrency in `test_conflict_postgres.py` | none yet (exception-shaped, not a status object) | **Traced, not adapted** — this scenario is proven by an exception path, not a value the schema can wrap without inventing a new shape for what's actually working correctly today |
| 6 | Partial load/resume | `ExpectedProducerStatus.PENDING`; `FilingArtifactSilverAcceptanceResult.interval_complete`/`unsettled_candidate_ids` (Ticket 19/29) | `from_expected_producer_status` | **Bound** |
| 7 | Out-of-order delivery | `test_seal_blocks_while_prior_revision_pending` / `test_seal_blocks_forever_after_prior_revision_failed_until_repaired` (Ticket 19); reserved, non-renumbered `Source Observation Position` (Ticket 18) — already traced in Ticket 04's asset, scenario 5 | none yet | **Traced, not adapted** — same shape as #5: proven by ordering/blocking behavior, not a status value |
| 8 | Repair attestation | `RevisionRelationship.REPAIR` (Ticket 25); `ConflictLedger` | none yet | **Traced, not adapted** — a `Repair Revision` is an immutable child revision, not yet mapped onto this schema's key-count shape; real future work, not built here |
| 9 | Bounded MDM closure | Ticket 06 decided 1-hop candidate-neighbor expansion; **Ticket 49 is unbuilt** (map's own tracer-bullet list: "Ready-for-agent", not "Resolved") | `unavailable(BOUNDED_MDM_CLOSURE, ...)` | **No populable source** |
| 10 | Gold affected-DAG selection | `GoldRefreshIdentity` (Ticket 39); Snowflake's own DAG-reactive `target_lag` refresh already proves selection is native, not Python-driven | none yet | **Traced, not adapted** — evidence is a Snowflake-native refresh timestamp per table, not a key list; binding it needs a real live read this ticket didn't scope |
| 11 | Unchanged graph-partition reuse | `MdmGraphGeneration`/`MdmGraphPartition` content-addressed reuse (Ticket 08/40) — mechanism proven by real tests, but `mdm sync-graph`'s live CLI path never calls `create_generation()`; `mdm_graph_generation` is confirmed **empty in prod** | none yet | **Mechanism proven, not live-wired** — different from unbuilt: the code exists and is tested, it just isn't reachable from the production caller yet (map's own "Not yet specified" note) |
| 12 | Full graph verification/activation | `SnowflakeGraphVerifier` / `mdm verify-graph`; `graph_parity_ok` (Ticket 41, stands in for MDM completeness) | none yet | **Traced, not adapted** — corrected after `/code-review`'s Spec axis caught an overclaim in this row's first draft: `from_cause_alignment` only ever tags its output `DECISION_WATERMARK_ALIGNMENT` (scenario 14); `graph_parity_ok` is consumed as one *input* to that alignment check, but no adapter ever produces a record tagged `GRAPH_VERIFICATION_ACTIVATION` itself |
| 13 | Reconciliation backstop | Ticket 38 designed `MDMPipeline.run_all()` with skip-if-unchanged off; **Ticket 50 is unbuilt** (same tracer-bullet status as #9) | `unavailable(RECONCILIATION_BACKSTOP, ...)` | **No populable source** |
| 14 | Aligned Decision Watermark | `CauseAlignment` / `rollup_business_date` / `evaluate_agent_grade` (Ticket 09/41) | `from_cause_alignment` | **Bound** |

## What this session actually built

Five scenarios (1, 2, 4, 6, 14) bind directly to existing evidence through
four small adapters — `from_content_impact`, `from_expected_producer_status`,
`from_parity_verdict`, `from_cause_alignment` — none of which re-derive
correctness logic a stage already proved. Scenario 12 (full graph
verification/activation) is traced but not separately adapted — see its
row above.

Three scenarios (5, 7, 8) are proven by real tests today but in a shape
(an exception, an ordering property, an immutable child revision) this
session did not force into the key-count schema — doing so would have
invented a new representation for something already working, which is the
Speculative-Generality failure mode `/gof-refactor-reviewer` exists to
catch.

Two scenarios (9, 13) are honestly `unavailable()` — Tickets 49/50 are not
yet built, confirmed live in this same session by checking their issue
files directly (no `Type:`/`Status:` header, marked "Ready-for-agent" in
the map's own tracer-bullet list, not "Resolved").

One scenario (3, RETIRE) has no shared cross-family evidence shape yet —
each family retires independently with its own row-count return value; a
real adapter needs that shared shape decided first, which is out of this
prototype's scope.

One scenario (10, gold affected-DAG) and one (11, graph-partition reuse)
have real evidence but binding either needs a live read (a Snowflake query,
a `mdm_graph_generation` row scan) this prototype ticket did not scope —
11 additionally surfaces a genuine production gap (the mechanism is
untested against live traffic because nothing calls it yet), separate from
"not built."

## Note on the frontier survey that led here

This map's own `/wayfinder` inventory (run earlier this session) reported
Tickets 49 and 50 as absent from the open/claimed list, because both
tickets lack the standard `Type:`/`Status:` header this repo's other
tickets use. They are genuinely unbuilt — confirmed directly against their
issue files while resolving this ticket — so a future survey of this map
should not trust header-absence as "nothing outstanding here."
