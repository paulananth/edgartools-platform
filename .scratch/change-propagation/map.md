# Incremental Change Propagation

Label: `wayfinder:map`

## Destination

An implementation-ready, decision-complete plan for propagating only new,
modified, or retired source facts—and their correctness-required Affected-Key
Closure—from bronze to silver, silver to MDM and gold, and MDM to the hosted
Neo4j graph, with deterministic replay and one aligned Decision Watermark.

## Notes

- Repo: `edgartools-platform`. Decision-spec only: this map plans the change;
  implementation happens in a later effort.
- AWS-only. Keep the current SEC EDGAR → warehouse CLI → S3/Snowflake → dbt →
  hosted graph architecture. Do not introduce another cloud, registry,
  workflow engine, storage target, or secret-management path.
- Scope locked during destination grilling on 2026-08-20:
  - Silver remains the Runtime System of Engagement and Bronze Persist remains
    optional. Bronze diffing is the exact replay/recovery path when bronze
    exists, not a requirement that every normal SEC request persist bronze.
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
  - Migration seeds a verified baseline, performs read-only reconciliation, and
    cuts over boundary-by-boundary without concurrent canonical writers.
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
  - [dbt Gold Silver Rewiring](../dbt-gold-silver-rewiring/map.md): existing
    vertical migrations away from Python full-snapshot gold builders.
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

## Not yet specified

- The physical coordinator topology and exact Step Functions/EventBridge Pipes
  ownership split; its shape depends on the stage-publication contracts.
- Post-cutover retention and cleanup of superseded DuckDB, mutable landing, and
  legacy SOURCE artifacts; the safe boundary depends on rollback design.
- Exact implementation phase/PR slicing and live rollout gates; these become
  specifiable after the acceptance artifact and migration sequence are locked.

## Out of scope

- Making Bronze Persist mandatory or replacing silver as the Runtime System of
  Engagement.
- Re-deciding the settled AWS messaging substrate, per-accession event grain,
  on-demand compute stance, Snowflake-native silver target, or DuckDB retirement.
- Physical deletion of SEC history, best-effort partial graph activation, or
  exposing a misaligned watermark as agent-grade.
- Non-AWS deployment/storage paths, broker execution, portfolio management, or
  unrelated dashboard/product work.
- Implementing, deploying, or production-validating the plan inside this map.
