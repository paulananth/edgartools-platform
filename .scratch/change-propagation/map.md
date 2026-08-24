# Incremental Change Propagation

Label: `wayfinder:map`

## Destination

An implementation-ready, decision-complete plan for propagating only new,
modified, or retired source facts—and their correctness-required Affected-Key
Closure—from bronze to silver, silver to MDM and gold, and MDM to the hosted
Neo4j graph, with deterministic replay and one aligned Decision Watermark.

## Notes

- Repo: `edgartools-platform`. Originally decision-spec only; superseded
  2026-08-22 (Tickets 13-17 landed real, merged implementation, not just
  decisions) — this map now also carries implementation and a first prod
  dry run through to Ticket 29. Per-source-family production cutover and
  ongoing operation still happen in a later effort.
- AWS-only. Keep the current SEC EDGAR → warehouse CLI → S3/Snowflake → dbt →
  hosted graph architecture. Do not introduce another cloud, registry,
  workflow engine, storage target, or secret-management path.
- Scope locked during destination grilling and revised by Ticket 03 grilling on
  2026-08-21:
  - SEC is the external Source Authority; Bronze is the mandatory immutable
    evidence store for every successful relevant response; PostgreSQL is the
    sole local authority for acquisition and processing state; and Silver
    remains the authoritative Runtime System of Engagement for published
    business state.
  - Every SEC request requires a prior PostgreSQL Source Fetch Decision. A
    Logical Source Revision materializes only after verified Bronze capture,
    and PostgreSQL exposes one joined download/processing status per candidate.
  - A change includes `UPSERT`, `RETIRE`, and scoped replacement completion;
    history is preserved rather than physically deleted.
  - Delivery is at-least-once with content-addressed idempotency and
    deterministic convergence, not an infrastructure-level exactly-once claim.
  - Work is bounded by the Affected-Key Closure: directly changed inputs plus
    the entity, survivorship, relationship, and derived-table dependents needed
    for correctness—never unrelated full-universe work.
  - A Change Propagation Run is immutable and binds source versions/hashes,
    parser/schema versions, operation types, affected keys, expected producers,
    stage outcomes, and publication identities.
  - Silver, MDM, gold, and graph publish independently. A composite Decision
    Watermark becomes agent-grade only after every affected stage is complete
    and aligned.
  - MDM uses targeted re-resolution plus bounded match/survivorship closure and
    a periodic full-universe reconciliation backstop.
  - Gold refreshes the affected dbt dependency closure and records whether
    Snowflake performed incremental or full work.
  - The graph is an immutable candidate generation assembled from changed
    partitions plus content-addressed reuse of unchanged partitions, fully
    verified before atomic pointer activation.
  - Immutable manifests/deltas live in S3; cursors, leases, outbox entries, and
    outcome ledgers live in Snowflake Postgres, outside the silver artifact.
  - Initial bootstrap and recovery after ledger loss use an explicitly
    authorized Hybrid Source Baseline, complete non-serving Silver candidate,
    catch-up barrier, verification, and atomic activation into a new epoch.
  - Migration performs read-only reconciliation and cuts over
    boundary-by-boundary without concurrent canonical writers.
- Settled predecessor maps are inputs, not questions to reopen:
  - [Decoupled bronze pipeline](../decoupled-bronze-pipeline/map.md):
    S3→SNS→two SQS queues, per-accession completion events, N-or-timer batching,
    on-demand compute, retry/DLQ policy, and migration principles.
  - [Silver-on-Snowflake Migration](../silver-snowflake-migration/map.md) and
    [DuckDB Retirement](../duckdb-retirement/map.md): append-only Snowflake
    landing, dbt-native silver, Snowflake Postgres operational bookkeeping, and
    retirement of DuckDB readers/writers.
  - [MDM Entity Resolution Ahead of Silver](../mdm-ahead-of-silver/map.md):
    two-phase Snowflake backfill and independent sweep semantics.
  - [dbt Gold Silver Rewiring tickets](../dbt-gold-silver-rewiring/issues/):
    existing vertical migrations away from Python full-snapshot gold builders.
- Current-head facts established before charting:
  - Bronze replay selects complete CIK directories and has no durable consumed
    object/version cursor; an intact old checkpoint can mask a newer bronze
    snapshot.
  - Silver landing objects use table/date/run paths that collide when multiple
    windows share one execution run ID; current landing rows also lack
    tombstones and scope-completion records.
  - MDM change detection is company-only by content hash; other entity and
    relationship paths rescan broadly or fail to requeue modified rows.
  - The legacy gold path still builds full snapshots, and normal graph workflow
    tails can sync a new generation while verifying the previously active one.
- Use `/grilling` and `/domain-modeling` for grilling tickets, `/prototype` for
  concrete contract artifacts, and a `/research` subagent for research tickets.
  Before any later code change or restructuring proposal, use
  `/gof-refactor-reviewer` against the relevant code and git history; leave the
  design alone unless current costs justify a pattern.
- Acceptance must cover no-op replay, modification, retirement, scoped
  replacement, concurrent producers, partial failure/resume, out-of-order
  delivery, unchanged graph-partition reuse, bounded reconciliation, and an
  aligned Decision Watermark—with measured proof that unrelated rows were not
  processed.

## Decisions so far

<!-- Closed ticket decisions: one-line gist and link; detail stays in the ticket. -->

- [Verify Snowflake incremental change-processing primitives](issues/01-verify-snowflake-incremental-primitives.md) — Snowflake supports bounded incremental publication and aligned refresh evidence, but the application run ledger must own the non-atomic cross-stage barrier.
- [Inventory table-specific change and dependency semantics](issues/02-inventory-table-change-semantics.md) — All 31 landing tables are mapped; current writers lack a shared retirement/no-op contract, local replacement deletes do not propagate, and MDM/graph closure is dispersed rather than registry-owned.
- [Decide the Bronze capture, consumption ledger, and source cursor contract](issues/03-decide-bronze-consumption-ledger.md) — SEC owns source truth, mandatory verified Bronze owns raw evidence, PostgreSQL owns local acquisition/processing state, and Silver owns published business state; ledger-gated capture uses a narrow Facade, executable family policies, and bundled acquisition handlers while scope proof, status, and epoch recovery fail closed.
- [13 — Expand acquisition command registration](issues/13-expand-acquisition-command-registration.md) — Behavior-preserving Command registration seam landed; `capture-filing-artifact` and `drive-filing-discovery-for-date` are both migrated through it, unregistered commands untouched (PR #445, merged `d30cbfd8`).
- [14 — Establish the acquisition ledger and status spine](issues/14-establish-acquisition-ledger-status-spine.md) — PostgreSQL fenced ledger (`AcquisitionLedger`, role-owned transitions, monotonic observation positions) live; a no-download candidate resolves without network access (PR #445, merged `d30cbfd8`).
- [15 — Capture one filing-artifact family through the gated Facade](issues/15-capture-filing-artifact-through-gated-facade.md) — Non-bypassable capture Facade plus the `filing_artifact` Source Family Registry Strategy prove content-addressed Bronze capture with durable artifact-reference finalization; manually smoke-tested against real Postgres + a real live SEC filing (PR #446, merged `6e4079cc`).
- [16 — Drive filing capture from SEC change discovery](issues/16-drive-filing-capture-from-sec-change-discovery.md) — `drive-filing-discovery-for-date` seals the daily index into a digested Discovery Manifest and issues one Fetch Decision per candidate, replay-safe and per-candidate fault-isolated (PR #447, merged `bae5637e`).
- [17 — Make Bronze capture retry-safe and recoverable](issues/17-make-bronze-capture-retry-safe.md) — Retry-after-failure, durable Fetch Attempt evidence, and lease-gated orphan quarantine all land; a real Postgres-only stale-fencing-token exception-translation gap (found by Spec review) is fixed and regression-tested. 304/conditional-GET linking is deliberately deferred to [Ticket 28](issues/28-add-conditional-fetch-and-not-modified-linking.md) — no live caller exists yet for it.
- [18 — Materialize ordered logical source revisions](issues/18-materialize-ordered-logical-source-revisions.md) — New `SourceRevisionLedger` and `source_revision` table (own `edgartools_acquisition_processor` role) materialize immutable, ordered Logical Source Revisions from CAPTURED decisions or from parser/schema reinterpretation of already-verified Bronze evidence, with real-thread concurrency proof and behavioral identity tests. Ticket 04's blocking edge was stale for this subset — Ticket 03's own answer already named the three hashes, completeness declaration, and revision-identity composition; Ticket 04 stays open for the run-manifest/expected-producer-set/replay-linkage portions later stages still need.
- [19 — Complete the filing-to-Silver acceptance seam](issues/19-complete-filing-to-silver-acceptance-seam.md) — New `ProcessingLedger`/`SilverFinalizer` (generic, own `edgartools_acquisition_silver_finalizer` role) seal expected Silver producers per revision and record read-back-verified outcomes; `filing_artifact`'s bounded first slice writes/reads back DuckDB's `sec_raw_object`. Same-key ordering is DB-backed (partial unique index) plus a plain committed read — `SELECT ... FOR UPDATE` was tried and rejected live (PostgreSQL requires UPDATE privilege the processor role deliberately lacks). Ticket 05's blocking edge was stale for this DuckDB-targeted subset; stays open for the real Snowflake delta-publication contract.

## Ticket 03 implementation tickets

<!-- Agent-grabbable tracer bullets; blocking edges live in each ticket. -->

- [19 — Complete the filing-to-Silver acceptance seam](issues/19-complete-filing-to-silver-acceptance-seam.md) — Verify publication or explicit non-publication while protecting prior Silver authority.
- [20 — Version and activate the Acquisition Universe](issues/20-version-and-activate-acquisition-universe.md) — Gate coverage changes on scoped baseline and catch-up proof.
- [21 — Migrate submissions snapshots and pagination](issues/21-migrate-submissions-and-pagination.md) — Deliver complete inventory-aware submissions processing.
- [22 — Migrate company-facts snapshots](issues/22-migrate-company-facts-snapshots.md) — Deliver complete scoped company-facts lifecycle outcomes.
- [23 — Migrate reference catalogs](issues/23-migrate-reference-catalogs.md) — Deliver counted and digested catalog completeness.
- [24 — Migrate ADV sources](issues/24-migrate-adv-sources.md) — Deliver filing and bulk-source ADV outcomes with explicit scopes.
- [25 — Add conflict, repair, exclusion, and evidence-import workflows](issues/25-add-conflict-repair-and-evidence-import.md) — Give operators auditable exceptional-evidence controls.
- [26 — Rebuild and activate a ledger epoch](issues/26-rebuild-and-activate-ledger-epoch.md) — Recover authority through a Hybrid Source Baseline and atomic activation.
- [27 — Contract legacy acquisition bypasses](issues/27-contract-legacy-acquisition-bypasses.md) — Remove bypasses only after every source family proves the authoritative path.
- [28 — Add conditional-fetch validators and not-modified linking](issues/28-add-conditional-fetch-and-not-modified-linking.md) — Surfaced while resolving Ticket 17: a due-poll conditional-GET path needs a new ledger read API and has no live caller yet.
- [29 — Deploy the gated acquisition path to prod and dry-run it](issues/29-deploy-and-dry-run-gated-acquisition-path.md) — Blocked by 18 and 19: apply migration 013, deploy current images, and observe a real bounded diff (capture through Silver acceptance) plus a no-op replay against real prod infrastructure.

## Not yet specified

- The physical coordinator topology and exact Step Functions/EventBridge Pipes
  ownership split; its shape depends on the stage-publication contracts.
- Post-cutover retention and cleanup of superseded DuckDB, mutable landing, and
  legacy SOURCE artifacts; the safe boundary depends on rollback design.
- Exact production canary thresholds and live rollout gates; these become
  specifiable after the acceptance artifact and migration sequence are locked.

## Out of scope

- Replacing Silver as the Runtime System of Engagement or treating Bronze as a
  competing processing-state authority beside PostgreSQL.
- Re-deciding the settled AWS messaging substrate, per-accession event grain,
  on-demand compute stance, Snowflake-native silver target, or DuckDB retirement.
- Physical deletion of SEC history, best-effort partial graph activation, or
  exposing a misaligned watermark as agent-grade.
- Non-AWS deployment/storage paths, broker execution, portfolio management, or
  unrelated dashboard/product work.
- Full-universe production cutover for every source family, and ongoing
  production operation of the gated path — Ticket 29 covers only a first,
  bounded, single-family prod dry run; broader rollout is a later effort.
